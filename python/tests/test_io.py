"""Tests for irpanel.io, the same spot checks the R readers used. Each test
runs against the real source files and skips when they are absent."""

import pandas as pd
import pytest

from conftest import skip_unless_exists
from irpanel import io


def test_read_pwt(config):
    skip_unless_exists(config["paths"]["source"] / config["inputs"]["pwt"],
                       "PWT file")
    pwt = io.read_pwt(config)
    assert list(pwt.columns) == ["iso3", "year", "gdppc"]
    assert (pwt["iso3"].str.len() == 3).all()
    assert pwt["iso3"].notna().all()
    assert (pwt["gdppc"] > 0).all()
    usa = pwt.loc[(pwt["iso3"] == "USA") & (pwt["year"] == 2019), "gdppc"]
    assert 40_000 < usa.iloc[0] < 100_000


def test_read_ssp(config):
    src = config["paths"]["source"]
    skip_unless_exists(src / config["inputs"]["ssp_snap_proj"], "SSP snapshot")
    skip_unless_exists(src / config["inputs"]["ssp_snap_hist"], "SSP snapshot")
    ssp = io.read_ssp(config)
    assert set(ssp) == {"gdppc", "pop", "cohorts"}

    gd = ssp["gdppc"]
    assert list(gd.columns) == ["model", "scenario", "iso3", "year", "gdppc"]
    assert set(gd["model"]) == {"OECD", "IIASA"}
    assert (gd["iso3"].str.len() == 3).all()
    assert gd["iso3"].notna().all()
    # IIASA per capita starts at 2025 in the SSP snapshot.
    assert gd.loc[gd["model"] == "IIASA", "year"].min() == 2025

    pop = ssp["pop"]
    assert set(pop["era"]) == {"historical", "projection"}
    assert pop["iso3"].notna().all()
    assert (pop["pop"] >= 0).all()

    coh = ssp["cohorts"]
    for col in ("age0to4", "age5to64", "age65plus"):
        assert (coh[col] >= 0).all()

    # Cohorts sum close to total population for a projection slice.
    ps = pop[(pop["era"] == "projection") & (pop["scenario"] == "SSP2")
             & (pop["year"] == 2050)][["iso3", "pop"]]
    cs = coh[(coh["era"] == "projection") & (coh["scenario"] == "SSP2")
             & (coh["year"] == 2050)].copy()
    cs["csum"] = cs["age0to4"] + cs["age5to64"] + cs["age65plus"]
    m = ps.merge(cs[["iso3", "csum"]], on="iso3")
    assert (m["pop"] - m["csum"]).abs().max() < 1


def test_read_kummu(config):
    src = config["paths"]["source"]
    skip_unless_exists(src / config["inputs"]["kummu_adm0"], "Kummu adm0")
    km = io.read_kummu(config)
    assert set(km) == {"adm0", "gdp_rast_path", "pop_rast_path"}
    adm0 = km["adm0"]
    assert list(adm0.columns) == ["iso3", "year", "gdppc"]
    assert (adm0["iso3"].str.len() == 3).all()
    assert adm0["year"].between(1990, 2022).all()
    assert km["gdp_rast_path"].exists()
    assert km["pop_rast_path"].exists()


def test_read_wpp(config):
    skip_unless_exists(config["paths"]["source"] / config["inputs"]["wpp"],
                       "WPP file")
    wpp = io.read_wpp(config)
    assert list(wpp.columns) == ["iso3", "year", "pop"]
    assert (wpp["iso3"].str.len() == 3).all()
    assert (wpp["pop"] > 0).all()
    assert wpp["year"].min() <= 1950 and wpp["year"].max() >= 2100
    assert not wpp.duplicated(["iso3", "year"]).any()
    usa = wpp.loc[(wpp["iso3"] == "USA") & (wpp["year"] == 2020), "pop"]
    assert 300 < usa.iloc[0] < 360


def test_ir_shapes_order_matches_r(config):
    """pyogrio must read polygons in the same order sf::st_read gave the R
    side, because the aggregation writes extract results in polygon order.
    Anchor: the first year-block of the R cache ir_pop_ghs.csv is in that
    polygon order."""
    pytest.importorskip("pyogrio")
    import pyogrio

    shp_path = config["paths"]["ir_shapes"]
    cache_csv = config["paths"]["cache"] / "ir_pop_ghs.csv"
    skip_unless_exists(shp_path, "IR shapefile")
    skip_unless_exists(cache_csv, "R aggregation cache")

    attrs = pyogrio.read_dataframe(shp_path, columns=["hierid"],
                                   read_geometry=False)
    assert len(attrs) > 24_000
    block = pd.read_csv(cache_csv, nrows=len(attrs))
    assert block["year"].nunique() == 1, "anchor block is not a single year"
    assert (attrs["hierid"].to_numpy() == block["hierid"].to_numpy()).all()


def test_read_ssp_stacks_snapshots(config):
    """Several projection snapshots stack; a repeated model/scenario row is
    an error (mirrors the R test)."""
    src = config["paths"]["source"]
    skip_unless_exists(src / config["inputs"]["ssp_snap_proj"],
                       "SSP snapshot")
    single = io.read_ssp(config)

    cfg_list = {**config,
                "inputs": {**config["inputs"],
                           "ssp_snap_proj":
                               [config["inputs"]["ssp_snap_proj"]]}}
    stacked = io.read_ssp(cfg_list)
    pd.testing.assert_frame_equal(stacked["gdppc"], single["gdppc"])

    cfg_dup = {**config,
               "inputs": {**config["inputs"],
                          "ssp_snap_proj":
                              [config["inputs"]["ssp_snap_proj"]] * 2}}
    with pytest.raises(ValueError, match="duplicate"):
        io.read_ssp(cfg_dup)
