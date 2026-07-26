"""Spatial aggregation of the Kummu rasters to IR polygons, mirroring
R/aggregate_grid.R.

Expensive (exactextract over ~24,378 polygons x 33 bands), so the results are
cached as CSVs and downstream modules read the cache. exactextract is the same
C++ zonal-statistics engine as R's exactextractr, so partial-pixel coverage
fractions match. The Python cache goes to its own directory (cache/py) so the
R cache stays intact.
"""

import re
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyproj
import rasterio
from exactextract import exact_extract


def _band_years(path):
    """Years parsed from the band descriptions (one four-digit year each)."""
    with rasterio.open(path) as d:
        return [int(re.search(r"[0-9]{4}", s).group()) for s in d.descriptions]


def _op_matrix(res, op):
    """Columns of one exactextract op as an (n_features, n_bands) array.

    exactextract names columns per band ("band_3_mean") or bare for a single
    band ("mean", "weight_weighted_mean"); select by suffix, ordered by band.
    """
    pat = re.compile(rf"^(?:band_(\d+)_)?(?:weight_)?{op}$")
    hits = sorted(((int(m.group(1) or 1), c) for c in res.columns
                   if (m := pat.match(c))), key=lambda t: t[0])
    return res[[c for _, c in hits]].to_numpy()


def _extract_to_long(mat, ids, years, value_name):
    """Turn an extract matrix (one column per band) into a long table keyed
    on hierid, iso3, year. Row order matches the polygon order in ids."""
    df = pd.DataFrame(mat, columns=years)
    df = pd.concat([ids.reset_index(drop=True), df], axis=1)
    long = df.melt(id_vars=["hierid", "iso3"], var_name="year",
                   value_name=value_name)
    long["year"] = long["year"].astype(int)
    return long


def cell_area_km2(shape, transform):
    """Per-cell geodesic area (km2) for a regular lon-lat grid, matching
    terra::cellSize: each cell as a geodesic rectangle on the WGS84 ellipsoid
    (verified against terra to ~1e-12 relative). Cells in a row share their
    area, so one rectangle per row is computed and broadcast."""
    height, width = shape
    geod = pyproj.Geod(ellps="WGS84")
    x0 = transform.c
    res_x = transform.a
    res_y = -transform.e
    row_areas = np.empty(height)
    for i in range(height):
        lat_hi = transform.f - i * res_y
        lat_lo = lat_hi - res_y
        lons = [x0, x0 + res_x, x0 + res_x, x0]
        lats = [lat_lo, lat_lo, lat_hi, lat_hi]
        row_areas[i] = abs(geod.polygon_area_perimeter(lons, lats)[0]) / 1e6
    return np.repeat(row_areas[:, None], width, axis=1)


def _write_band(profile, data, path, nodata):
    """Write one float band to a GeoTIFF for an exactextract input."""
    profile = dict(profile, count=1, dtype="float64", nodata=nodata,
                   driver="GTiff")
    with rasterio.open(path, "w", **profile) as d:
        d.write(data.astype("float64"), 1)
    return str(path)


def aggregate_kummu_to_ir(kummu, ir_shapes, config):
    """Aggregate Kummu GDP and GHS-POP rasters to IR polygons and cache the
    result under the Python cache path.

    :param kummu: output of read_kummu() (adm0, gdp_rast_path, pop_rast_path).
    :param ir_shapes: output of read_ir_shapes() (GeoDataFrame keyed on
        hierid).
    :param config: parsed config dict.
    :return: dict(gdppc, pop, density, validation); each is also written as a
        CSV under config paths cache_py.
    """
    gdp_path = str(kummu["gdp_rast_path"])
    pop_path = str(kummu["pop_rast_path"])
    with rasterio.open(gdp_path) as g, rasterio.open(pop_path) as p:
        if g.transform != p.transform or g.shape != p.shape:
            raise ValueError("GDP and population rasters do not align")
        profile = p.profile
        shape, transform = p.shape, p.transform
    gdp_years = _band_years(gdp_path)
    pop_years = _band_years(pop_path)

    ids = pd.DataFrame({
        "hierid": ir_shapes["hierid"],
        "iso3": ir_shapes["hierid"].str.replace(r"\..*", "", regex=True),
    })

    tmp = Path(tempfile.mkdtemp(prefix="irpanel_agg_"))

    # GDP per capita: population-weighted mean, weights = GHS-POP at the base
    # year with missing set to 0 (as the R classify does). Where the weight
    # sums to zero the mean is NaN; fall back to the coverage-weighted area
    # mean and flag those IRs.
    wy = config["aggregation"]["pop_weight_year"]
    wi = pop_years.index(wy)
    with rasterio.open(pop_path) as p:
        weight = np.nan_to_num(p.read(wi + 1))
    weight_tif = _write_band(profile, weight, tmp / "weight.tif", None)
    print("Aggregating GDP per capita (population-weighted mean)...")
    res = exact_extract(gdp_path, ir_shapes, ["weighted_mean", "mean"],
                        weights=weight_tif, output="pandas")
    wmean = _op_matrix(res, "weighted_mean")
    amean = _op_matrix(res, "mean")
    gdppc = _extract_to_long(wmean, ids, gdp_years, "gdppc_w").merge(
        _extract_to_long(amean, ids, gdp_years, "gdppc_a"),
        on=["hierid", "iso3", "year"])
    gdppc["zero_pop"] = gdppc["gdppc_w"].isna()
    gdppc["gdppc"] = np.where(gdppc["zero_pop"], gdppc["gdppc_a"],
                              gdppc["gdppc_w"])
    gdppc = gdppc[["hierid", "iso3", "year", "gdppc", "zero_pop"]]
    n_fb = gdppc.loc[gdppc["zero_pop"], "hierid"].nunique()
    print(f"  {n_fb} IRs used the area-mean fallback (zero population weight)")

    # Population: coverage-weighted zonal sum, all years.
    print("Aggregating population (zonal sum)...")
    res = exact_extract(pop_path, ir_shapes, ["sum"], output="pandas")
    pop_ir = _extract_to_long(_op_matrix(res, "sum"), ids, pop_years, "pop")

    # Population-weighted density: the density the average resident
    # experiences, sum(density_j * pop_j * cov) / sum(pop_j * cov) with
    # density_j = pop_j / area_j. Done a year at a time on single-band
    # rasters to keep memory small; zero-population IRs give NaN, set to 0.
    print("Aggregating population-weighted density...")
    area = cell_area_km2(shape, transform)
    pwd_cols = []
    with rasterio.open(pop_path) as p:
        for i in range(len(pop_years)):
            band = p.read(i + 1)
            dens_tif = _write_band(profile, band / area, tmp / "dens.tif",
                                   np.nan)
            wt_tif = _write_band(profile, band, tmp / "wt.tif", np.nan)
            res = exact_extract(dens_tif, ir_shapes, ["weighted_mean"],
                                weights=wt_tif, output="pandas")
            pwd_cols.append(_op_matrix(res, "weighted_mean")[:, 0])
    density = _extract_to_long(np.column_stack(pwd_cols), ids, pop_years,
                               "pop_wtd_density")
    density["pop_wtd_density"] = density["pop_wtd_density"].fillna(0)

    # Validation: national population-weighted mean of the IR GDP per capita,
    # compared with the Kummu ADM0 table.
    print("Validating national averages against Kummu ADM0...")
    nat = gdppc[gdppc["gdppc"].notna()].merge(
        pop_ir, on=["hierid", "iso3", "year"])
    nat = nat[nat["pop"] > 0]
    natavg = (nat.groupby(["iso3", "year"])
              .apply(lambda g: np.average(g["gdppc"], weights=g["pop"]),
                     include_groups=False)
              .rename("gdppc_natavg").reset_index())
    adm0 = kummu["adm0"].rename(columns={"gdppc": "gdppc_adm0"})
    validation = natavg.merge(adm0, on=["iso3", "year"])
    validation["ratio"] = (validation["gdppc_natavg"]
                           / validation["gdppc_adm0"])
    validation["pct_diff"] = (validation["gdppc_natavg"]
                              - validation["gdppc_adm0"]) \
        / validation["gdppc_adm0"] * 100
    vy = validation[validation["year"] == wy]
    thr = config["aggregation"]["validation_pct"]
    print(f"  Year {wy}: median ratio {vy['ratio'].median():.4f}, "
          f"{int((vy['pct_diff'].abs() > thr).sum())} countries over {thr}%")

    cache = config["paths"]["cache_py"]
    cache.mkdir(parents=True, exist_ok=True)
    gdppc.to_csv(cache / "ir_gdppc_kummu.csv", index=False)
    pop_ir.to_csv(cache / "ir_pop_ghs.csv", index=False)
    density.to_csv(cache / "ir_pop_wtd_density.csv", index=False)
    validation.to_csv(cache / "ir_kummu_validation.csv", index=False)
    print(f"Cached 4 CSVs under {cache}")

    return {"gdppc": gdppc, "pop": pop_ir, "density": density,
            "validation": validation}
