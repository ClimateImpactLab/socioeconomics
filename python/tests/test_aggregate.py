"""Tests for irpanel.aggregate. The R semantics get a synthetic micro-raster
test (partial pixels, zero-pop fallback, no-overlap NA); the cell-area grid
gets a hand check; the cache-to-cache comparison against the R CSVs runs when
both caches are present (the cluster, or locally after `irpanel aggregate`)."""

import numpy as np
import pandas as pd
import pytest

rasterio = pytest.importorskip("rasterio")
gpd = pytest.importorskip("geopandas")

from rasterio.transform import from_origin  # noqa: E402
from shapely.geometry import box  # noqa: E402

from conftest import skip_unless_exists  # noqa: E402
from irpanel import aggregate  # noqa: E402

CACHE_FILES = ("ir_gdppc_kummu.csv", "ir_pop_ghs.csv",
               "ir_pop_wtd_density.csv", "ir_kummu_validation.csv")


def _write_raster(path, bands, descs):
    arr = np.array(bands, dtype="float64")
    # No CRS on purpose: exactextract only needs aligned grids, and writing
    # an EPSG code would require PROJ database access the test suite should
    # not depend on.
    with rasterio.open(path, "w", driver="GTiff", height=2, width=2,
                       count=len(bands), dtype="float64", nodata=np.nan,
                       transform=from_origin(0, 2, 1, 1)) as d:
        d.write(arr)
        for i, s in enumerate(descs):
            d.set_band_description(i + 1, s)
    return path


@pytest.fixture()
def micro(tmp_path):
    """Two IRs on a 2x2 grid, one year. AAA.1 is the left column (pop 2 and
    6), AAA.2 the top-right cell (pop 0: zero-weight fallback), BBB.1 sits
    off-grid (no overlap). GDP bottom-right is missing."""
    gdp = _write_raster(tmp_path / "gdp.tif",
                        [[[100.0, 200.0], [300.0, np.nan]]], ["gdp_pc_2020"])
    pop = _write_raster(tmp_path / "pop.tif",
                        [[[2.0, 0.0], [6.0, np.nan]]], ["pop2020"])
    # CRS via pyproj on the vector side only (exactextract requires one);
    # the rasters stay CRS-less so the test does not depend on rasterio's
    # PROJ database.
    shapes = gpd.GeoDataFrame({
        "hierid": ["AAA.1", "AAA.2", "BBB.1"],
        "geometry": [box(0, 0, 1, 2), box(1, 1, 2, 2), box(5, 5, 6, 6)],
    }, crs="EPSG:4326")
    kummu = {
        "gdp_rast_path": gdp, "pop_rast_path": pop,
        "adm0": pd.DataFrame({"iso3": ["AAA"], "year": [2020],
                              "gdppc": [250.0]}),
    }
    config = {"paths": {"cache_py": tmp_path / "cache"},
              "aggregation": {"pop_weight_year": 2020, "validation_pct": 5}}
    return kummu, shapes, config


def test_micro_aggregation(micro):
    kummu, shapes, config = micro
    out = aggregate.aggregate_kummu_to_ir(kummu, shapes, config)

    g = out["gdppc"].set_index("hierid")
    # AAA.1: weighted mean over its two cells, weights 2 and 6.
    assert np.isclose(g.loc["AAA.1", "gdppc"],
                      (100 * 2 + 300 * 6) / 8)
    assert not g.loc["AAA.1", "zero_pop"]
    # AAA.2: its only cell has pop 0 -> area-mean fallback, flagged.
    assert g.loc["AAA.2", "zero_pop"]
    assert np.isclose(g.loc["AAA.2", "gdppc"], 200.0)
    # BBB.1: no overlap with the grid -> NA, flagged by the NaN weight sum.
    assert np.isnan(g.loc["BBB.1", "gdppc"])

    p = out["pop"].set_index("hierid")["pop"]
    assert np.isclose(p["AAA.1"], 8.0)  # NaN pop cell contributes nothing
    assert np.isclose(p["AAA.2"], 0.0)
    assert p["BBB.1"] == 0 or np.isnan(p["BBB.1"])

    d = out["density"].set_index("hierid")["pop_wtd_density"]
    # AAA.1: sum(dens*pop)/sum(pop) with dens = pop/area per cell.
    area = aggregate.cell_area_km2((2, 2), from_origin(0, 2, 1, 1))
    expect = ((2 / area[0, 0]) * 2 + (6 / area[1, 0]) * 6) / 8
    assert np.isclose(d["AAA.1"], expect, rtol=1e-6)
    assert d["AAA.2"] == 0  # zero-pop -> NaN -> filled 0
    assert d["BBB.1"] == 0

    v = out["validation"]
    natavg = (100 * 2 + 300 * 6) / 8  # only AAA.1 has pop > 0
    assert np.isclose(v.loc[0, "gdppc_natavg"], natavg)
    assert np.isclose(v.loc[0, "ratio"], natavg / 250.0)

    for fname in CACHE_FILES:
        assert (config["paths"]["cache_py"] / fname).exists()


def test_cell_area_hand_check():
    """Cell areas match terra::cellSize (geodesic rectangles, WGS84): the
    5-arcmin equator cell is ~85.48 km2 and rows share areas symmetric about
    the equator."""
    t = rasterio.transform.from_origin(-180, 90, 1 / 12, 1 / 12)
    area = aggregate.cell_area_km2((2160, 4320), t)
    assert np.isclose(area[1080, 0], 85.4796530573, rtol=1e-9)
    assert np.isclose(area[0, 0], 0.0630032463, rtol=1e-6)
    assert np.allclose(area[:, 0], area[::-1, 0])  # symmetric N/S
    assert (area[:, 0] == area[:, -1]).all()  # rows constant


def test_cache_to_cache(config):
    """The Python cache reproduces the R cache per hierid and year, outside
    the documented residual set (docs/python-reproduction.md): impact
    regions with degenerate shapefile geometry that GEOS (Python) and s2
    (R) repair differently. The residual set must not grow."""
    r_cache = config["paths"]["cache"]
    py_cache = config["paths"]["cache_py"]
    for f in CACHE_FILES:
        skip_unless_exists(r_cache / f, f"R cache {f}")
        skip_unless_exists(py_cache / f, f"Python cache {f}")
    from irpanel.config import find_repo_root

    residual_path = find_repo_root() / "docs" / "residual_irs.csv"
    residual = set(pd.read_csv(residual_path)["hierid"])
    residual_iso = {h.split(".")[0] for h in residual}
    for fname in CACHE_FILES:
        r = pd.read_csv(r_cache / fname)
        py = pd.read_csv(py_cache / fname)
        keys = [k for k in ("hierid", "iso3", "year") if k in r.columns]
        m = py.merge(r, on=keys, suffixes=("_py", "_r"), how="outer",
                     indicator=True)
        assert (m["_merge"] == "both").all(), fname
        if "hierid" in m.columns:
            m = m[~m["hierid"].isin(residual)]
        else:
            # The validation table is national; countries containing a
            # residual region inherit its divergence.
            m = m[~m["iso3"].isin(residual_iso)]
        for col in [c[:-3] for c in m.columns if c.endswith("_py")]:
            if col in ("ratio", "pct_diff"):
                # Derived from gdppc_natavg/gdppc_adm0; pct_diff hovers
                # near zero, where a relative comparison is ill-conditioned.
                continue
            if m[f"{col}_py"].dtype.kind != "f":
                assert m[f"{col}_py"].equals(m[f"{col}_r"]), f"{fname}:{col}"
                continue
            a = m[f"{col}_py"].to_numpy(dtype=float)
            b = m[f"{col}_r"].to_numpy(dtype=float)
            assert (np.isnan(a) == np.isnan(b)).all(), f"{fname}:{col}"
            with np.errstate(divide="ignore", invalid="ignore"):
                pct = np.abs(a - b) / np.abs(b) * 100
            pct[(b == 0) & (a == 0)] = 0.0
            pct[np.isnan(a) & np.isnan(b)] = 0.0
            assert np.nanmax(pct) < 1e-2, f"{fname}:{col}"
