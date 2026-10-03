"""Tests for irpanel.income. The full build runs once on the shared R cache
(skipped when cache or sources are absent) and validates against the reference
panel; the deliberate behaviors (growth cross-fill, Venezuela rule, the two
deflators) each get a focused test."""

import numpy as np
import pandas as pd
import pytest

from conftest import skip_unless_exists
from irpanel import income
from irpanel.compare import pct_diff_stats
from irpanel.io import read_pwt


@pytest.fixture(scope="module")
def built(config):
    """Build income once for the data-backed tests."""
    skip_unless_exists(config["paths"]["cache"] / "ir_gdppc_kummu.csv",
                       "aggregation cache")
    skip_unless_exists(
        config["paths"]["source"] / config["inputs"]["ssp_snap_proj"],
        "SSP snapshot")
    return income.build_income(config, "SSP3", "IIASA")


def test_deflator_constants():
    # BEA GDP deflator (2017 = 100): 2005 = 81.556, 2021 = 110.186.
    assert income.PWT_TO_2005 == 81.556 / 110.186
    assert round(income.PWT_TO_2005, 5) == 0.74017
    assert income.KUMMU_TO_2005 == 0.81556


def test_growth_cross_fill():
    """The IIASA panel takes OECD growth for OECD-only countries and the OECD
    panel takes IIASA growth for IIASA-only countries (reference Step 3c)."""
    knots = np.arange(2020, 2101, 5)
    rows = []
    # AAA: OECD only. BBB: IIASA only. CCC: both.
    for iso3, models in (("AAA", ["OECD"]), ("BBB", ["IIASA"]),
                         ("CCC", ["OECD", "IIASA"])):
        for model in models:
            years = knots if model == "OECD" else knots[knots >= 2025]
            for i, year in enumerate(years):
                rows.append({"model": model, "scenario": "SSP3",
                             "iso3": iso3, "year": year,
                             "gdppc": 1000.0 * 1.02 ** i})
    ssp = pd.DataFrame(rows)

    iiasa = income.ssp_growth(ssp, "IIASA")
    oecd = income.ssp_growth(ssp, "OECD")

    assert {"AAA", "BBB", "CCC"} <= set(iiasa["iso3"])
    assert {"AAA", "BBB", "CCC"} <= set(oecd["iso3"])
    # The cross-filled country carries the other model's growth unchanged.
    aaa_iiasa = iiasa[iiasa["iso3"] == "AAA"].sort_values("year")
    aaa_oecd = oecd[oecd["iso3"] == "AAA"].sort_values("year")
    assert np.allclose(aaa_iiasa["growth"], aaa_oecd["growth"])
    # Growth is relative to 2023 and spans 2024-2100 for every country.
    for frame in (iiasa, oecd):
        spans = frame.groupby("iso3")["year"].agg(["min", "max"])
        assert (spans["min"] == 2024).all()
        assert (spans["max"] == 2100).all()


def test_venezuela_rule():
    """VEN 2012-2023 follows a log-linear national path from PWT 2011 to the
    IIASA 2025 level (deflated), keeping the Kummu subnational shares."""
    pwt = pd.DataFrame({"iso3": ["VEN"], "year": [2011], "pwt": [10_000.0]})
    ssp = pd.DataFrame({"model": ["IIASA"], "scenario": ["SSP3"],
                        "iso3": ["VEN"], "year": [2025], "gdppc": [20_000.0]})
    years = np.arange(2012, 2023)
    kummu_ir = pd.concat([
        pd.DataFrame({"hierid": "VEN.1", "iso3": "VEN", "year": years,
                      "kummu_ir": 100.0}),
        pd.DataFrame({"hierid": "VEN.2", "iso3": "VEN", "year": years,
                      "kummu_ir": 300.0}),
    ], ignore_index=True)
    adm0 = pd.DataFrame({"iso3": "VEN", "year": years, "kummu_nat": 200.0})

    out = income.venezuela_income(kummu_ir, adm0, pwt, ssp)

    s2025 = 20_000.0 * income.KUMMU_TO_2005
    nat = lambda y: 10_000.0 * np.exp(  # noqa: E731
        np.log(s2025 / 10_000.0) * (y - 2011) / 14)
    v1 = out[out["hierid"] == "VEN.1"].set_index("year")["gdppc"]
    assert set(out["year"]) == set(range(2012, 2024))
    assert np.isclose(v1[2015], 100.0 / 200.0 * nat(2015))
    assert np.isclose(v1[2023], 100.0 / 200.0 * nat(2022) * nat(2023)
                      / nat(2022))
    # Subnational shares survive: VEN.2 is 3x VEN.1 in every year.
    v2 = out[out["hierid"] == "VEN.2"].set_index("year")["gdppc"]
    assert np.allclose(v2 / v1, 3.0)

    # Missing anchors return None.
    assert income.venezuela_income(
        kummu_ir, adm0, pwt[pwt["year"] != 2011], ssp) is None


def test_columns_and_range(built):
    assert list(built.columns) == ["hierid", "iso3", "year", "scenario",
                                   "gdp_model", "gdppc"]
    assert built["year"].min() == 1990
    assert built["year"].max() == 2100
    assert (built["scenario"] == "SSP3").all()
    assert (built["gdp_model"] == "IIASA").all()


def test_no_pwt_deflation(built, config):
    """Countries absent from PWT keep raw Kummu deflated 2017 -> 2005."""
    cache = pd.read_csv(config["paths"]["cache"] / "ir_gdppc_kummu.csv")
    pwt_iso = set(read_pwt(config)["iso3"])
    no_pwt = (set(cache.loc[cache["gdppc"].notna(), "iso3"]) - pwt_iso)
    assert no_pwt, "expected at least one country without PWT"
    sample = cache[cache["iso3"].isin(no_pwt) & cache["gdppc"].notna()]
    m = sample.merge(built, on=["hierid", "iso3", "year"],
                     suffixes=("_kummu", ""))
    assert len(m)
    assert np.allclose(m["gdppc"], m["gdppc_kummu"] * income.KUMMU_TO_2005)


def test_pwt_deflation(built, config):
    """Historical income is the Kummu share times PWT deflated 2021 -> 2005."""
    from irpanel.io import read_kummu

    cache = pd.read_csv(config["paths"]["cache"] / "ir_gdppc_kummu.csv")
    adm0 = read_kummu(config)["adm0"]
    pwt = read_pwt(config)
    usa_pwt = pwt.loc[(pwt["iso3"] == "USA") & (pwt["year"] == 2010),
                      "gdppc"].iloc[0] * income.PWT_TO_2005
    usa_nat = adm0.loc[(adm0["iso3"] == "USA") & (adm0["year"] == 2010),
                       "gdppc"].iloc[0]
    sample = cache[(cache["iso3"] == "USA") & (cache["year"] == 2010)
                   & cache["gdppc"].notna()].head(20)
    m = sample.merge(built, on=["hierid", "iso3", "year"],
                     suffixes=("_kummu", ""))
    assert np.allclose(m["gdppc"], m["gdppc_kummu"] / usa_nat * usa_pwt)


def test_against_reference(built, config):
    """Raw income (missing as 0) matches the reference panel's gdppc_raw0 at
    the same level the R implementation reaches: median ~0, mean 0.028%
    (verified identical to the R build; the residual is shared, mostly
    countries the reference filled from sources outside PWT coverage)."""
    ref_path = config["paths"]["reference"] / config["inputs"]["reference"]
    skip_unless_exists(ref_path, "reference panel")
    ref = pd.read_csv(ref_path, usecols=["hierid", "year", "gdppc_raw0"])
    ref = ref[ref["year"] >= 1990]
    res = built[["hierid", "year", "gdppc"]].copy()
    res["gdppc"] = res["gdppc"].fillna(0)
    stats = pct_diff_stats(res, ref, ["hierid", "year"], "gdppc",
                           "gdppc_raw0")
    assert stats["n_result_only"] == 0
    assert stats["n_reference_only"] == 0
    assert stats["median_abs_pct"] < 1e-9
    assert stats["mean_abs_pct"] < 0.05


def test_force_gdp_sum_off(config):
    """Reproduction mode keeps the force_gdp_sum hook off."""
    assert not config["deltas"]["force_gdp_sum"]


def test_force_gdp_sum_scales_to_national(config):
    """Mirrors the R test: with force_gdp_sum on, IR GDP sums to the SSP
    national level from 2024 on, and the PWT-anchored years are untouched."""
    from irpanel.income import KUMMU_TO_2005, interp_annual
    from irpanel.io import read_ssp
    from irpanel.population import build_population
    skip_unless_exists(config["paths"]["cache"] / "ir_gdppc_kummu.csv",
                       "aggregation cache")
    cfg = {**config, "deltas": {**config["deltas"], "force_gdp_sum": True}}

    inc = income.build_income(cfg, "SSP3", "IIASA")
    pop = build_population(cfg, "SSP3")[["hierid", "year", "pop"]]
    ssp_gdppc = read_ssp(cfg)["gdppc"]
    ssp_gdppc = ssp_gdppc[ssp_gdppc["scenario"] == "SSP3"]
    nat = interp_annual(ssp_gdppc[ssp_gdppc["model"] == "IIASA"][
        ["iso3", "year", "gdppc"]])
    nat = nat[nat["year"] >= 2024].assign(
        nat_gdppc=lambda d: d["gdppc"] * KUMMU_TO_2005)

    x = inc.merge(pop, on=["hierid", "year"])
    x = x[x["gdppc"].notna() & (x["pop"] > 0)]
    sums = (x.assign(ir_gdp=x["gdppc"] * x["pop"])
            .groupby(["iso3", "year"], as_index=False)
            .agg(ir_gdp=("ir_gdp", "sum"), pop_nat=("pop", "sum")))
    chk = sums.merge(nat[["iso3", "year", "nat_gdppc"]],
                     on=["iso3", "year"])
    assert len(chk) > 10000
    target = chk["nat_gdppc"] * chk["pop_nat"]
    assert ((chk["ir_gdp"] - target).abs() / target).max() < 1e-9

    # PWT-anchored years are untouched.
    inc_off = income.build_income(config, "SSP3", "IIASA")
    pre = inc[inc["year"] <= 2023].merge(
        inc_off[inc_off["year"] <= 2023], on=["hierid", "year"],
        suffixes=("_on", "_off"))
    both = pre[pre["gdppc_on"].notna() & pre["gdppc_off"].notna()]
    assert np.allclose(both["gdppc_on"], both["gdppc_off"], rtol=1e-12)
