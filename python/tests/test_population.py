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
    """Only IIASA control totals are implemented; UN_WPP raises."""
    cfg = {**config, "deltas": {**config["deltas"], "pop_control": "UN_WPP"}}
    with pytest.raises(NotImplementedError):
        population.build_population(cfg, "SSP3")


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
