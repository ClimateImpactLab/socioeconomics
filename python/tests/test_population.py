"""Tests for irpanel.population. The full build runs once on the shared R
cache (skipped when cache or sources are absent); the deliberate behaviors
(linear interpolation, fixed vs year-specific shares, the pop_control guard)
each get a focused test."""

import numpy as np
import pandas as pd
import pytest

from conftest import skip_unless_exists
from irpanel import population
from irpanel.compare import pct_diff_stats


@pytest.fixture(scope="module")
def built(config):
    skip_unless_exists(config["paths"]["cache"] / "ir_pop_ghs.csv",
                       "aggregation cache")
    skip_unless_exists(
        config["paths"]["source"] / config["inputs"]["ssp_snap_proj"],
        "SSP snapshot")
    return population.build_population(config, "SSP3")


def test_linear_interpolation():
    """National population knots interpolate linearly (the R catch: income is
    log-linear, population is not)."""
    knots = pd.DataFrame({"iso3": ["AAA", "AAA"], "year": [2020, 2030],
                          "ssp_nat": [100.0, 200.0]})
    out = population.pop_linear_annual(knots)
    mid = out.loc[out["year"] == 2025, "ssp_nat"].iloc[0]
    assert mid == 150.0  # linear; log-linear would give ~141.42
    assert len(out) == 11
    # A single knot is dropped.
    single = pd.DataFrame({"iso3": ["BBB"], "year": [2020],
                           "ssp_nat": [10.0]})
    assert len(population.pop_linear_annual(single)) == 0


def test_pop_control_guard(config):
    """An unknown pop_control raises; IIASA and UN_WPP are implemented."""
    cfg = {**config, "deltas": {**config["deltas"], "pop_control": "bogus"}}
    with pytest.raises(ValueError, match="unknown pop_control"):
        population.build_population(cfg, "SSP3")


def test_un_wpp_handoff(config):
    """Mirrors the R test: under UN_WPP the IR sums match WPP through the
    handoff, SSP2 equals SSP3 at the handoff and differs by 2100, and the
    seam growth equals the SSP trajectory's own growth (no jump)."""
    pytest.importorskip("openpyxl")
    skip_unless_exists(config["paths"]["cache"] / "ir_pop_ghs.csv",
                       "aggregation cache")
    skip_unless_exists(
        config["paths"]["source"] / config["inputs"]["wpp"], "WPP source")
    cfg = {**config, "deltas": {**config["deltas"],
                                "pop_control": "UN_WPP",
                                "pop_handoff_year": 2023}}

    pop3 = population.build_population(cfg, "SSP3")
    s3 = (pop3.groupby(["iso3", "year"], as_index=False)["pop"].sum()
          .rename(columns={"pop": "ir_sum"}))

    # Through the handoff the IR sums match the WPP national totals.
    from irpanel.io import read_ssp, read_wpp
    wpp = read_wpp(cfg)
    chk = s3[s3["year"] <= 2023].merge(
        wpp.assign(wpp_nat=wpp["pop"] * 1e6)[["iso3", "year", "wpp_nat"]],
        on=["iso3", "year"])
    assert len(chk) > 5000
    rel = ((chk["ir_sum"] - chk["wpp_nat"]).abs() / chk["wpp_nat"]).max()
    assert rel < 1e-9

    # After the handoff the scenario matters.
    pop2 = population.build_population(cfg, "SSP2")
    s2 = (pop2.groupby(["iso3", "year"], as_index=False)["pop"].sum()
          .rename(columns={"pop": "ir_sum"}))
    at_h = s2[s2["year"] == 2023].merge(s3[s3["year"] == 2023], on="iso3",
                                        suffixes=("_2", "_3"))
    assert np.allclose(at_h["ir_sum_2"], at_h["ir_sum_3"], rtol=1e-12)
    assert not np.isclose(s2.loc[s2["year"] == 2100, "ir_sum"].sum(),
                          s3.loc[s3["year"] == 2100, "ir_sum"].sum())

    # No jump at the seam: India's 2023 -> 2024 growth equals the SSP's.
    ssp = read_ssp(cfg)["pop"]
    ssp = ssp[(ssp["era"] == "projection") & (ssp["scenario"] == "SSP3")]
    ann = population.pop_linear_annual(
        ssp[["iso3", "year", "pop"]].rename(columns={"pop": "ssp_nat"}))
    ind = ann[(ann["iso3"] == "IND")
              & ann["year"].isin((2023, 2024))].sort_values("year")
    g_ssp = ind["ssp_nat"].iloc[1] / ind["ssp_nat"].iloc[0]
    pan = s3[(s3["iso3"] == "IND")
             & s3["year"].isin((2023, 2024))].sort_values("year")
    g_pan = pan["ir_sum"].iloc[1] / pan["ir_sum"].iloc[0]
    assert abs(g_pan - g_ssp) < 1e-9


def test_columns_and_range(built):
    assert list(built.columns) == ["hierid", "iso3", "year", "scenario",
                                   "pop"]
    assert built["year"].min() == 1981
    assert built["year"].max() == 2100
    assert (built["pop"] >= 0).all()
    assert (built["scenario"] == "SSP3").all()


def test_projection_fixed_shares(built):
    """Projection years distribute national totals by fixed 2020 GHS shares:
    each IR's share of its country is constant over 2020-2100."""
    usa = built[(built["iso3"] == "USA") & (built["year"].isin((2020, 2050)))]
    shares = usa.assign(
        share=usa["pop"] / usa.groupby("year")["pop"].transform("sum"))
    wide = shares.pivot(index="hierid", columns="year", values="share")
    assert np.allclose(wide[2020], wide[2050])


def test_historical_year_specific_shares(built):
    """Historical years use year-specific GHS shares (they drift), frozen at
    the 1990 distribution before 1990."""
    usa = built[(built["iso3"] == "USA")
                & built["year"].isin((1985, 1990, 1995, 2015))]
    shares = usa.assign(
        share=usa["pop"] / usa.groupby("year")["pop"].transform("sum"))
    wide = shares.pivot(index="hierid", columns="year", values="share")
    assert np.allclose(wide[1985], wide[1990])  # frozen pre-1990
    assert not np.allclose(wide[1995], wide[2015])  # year-specific drift


def test_against_reference(built, config):
    """Population matches the reference panel at the level the R build
    reaches: median ~0, mean 0.105% (verified identical to R; the residual is
    shared, dominated by the reference's own share handling for Canada)."""
    ref_path = config["paths"]["reference"] / config["inputs"]["reference"]
    skip_unless_exists(ref_path, "reference panel")
    ref = pd.read_csv(ref_path, usecols=["hierid", "year", "pop"])
    stats = pct_diff_stats(built, ref, ["hierid", "year"], "pop")
    assert stats["n_result_only"] == 0
    assert stats["n_reference_only"] == 0
    assert stats["median_abs_pct"] < 1e-6
    assert stats["mean_abs_pct"] < 0.15
