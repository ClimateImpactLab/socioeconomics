"""Assemble the final IR panel, mirroring R/postprocess.R.

Applies the reference postprocessing: impute early income, Bartlett-smooth
from 2016, derive gdp and densities, and fill missing values with zero. The
smoothing kernel is the reference's backward half-Bartlett, ported behavior
for behavior: the oldest value in the window carries the highest weight.
"""

import numpy as np
import pandas as pd
import pyproj

from .cohorts import build_cohorts
from .income import build_income
from .io import read_ir_shapes
from .population import build_population

PANEL_COLS = ["hierid", "iso3", "year", "gdppc", "gdppc_raw", "gdppc_raw0",
              "gdp", "pop", "area_km2", "pop_density", "pop_wtd_density",
              "pop0to4", "pop5to64", "pop65plus"]


def bartlett_smooth(x, window=13):
    """Backward half-Bartlett kernel (window 13), as in the reference.

    For year i the weights are 13, 12, ... over the values from x[i - 12] to
    x[i], so the oldest value in the window carries the highest weight; at the
    start the window truncates and renormalises over the available lags.
    Missing values are skipped and the weights renormalised; an all-missing
    window gives NaN.

    :param x: 1-D series, or a 2-D array of series in rows (years in
        columns), smoothed independently per row.
    :return: array of the same shape.
    """
    arr = np.asarray(x, dtype=float)
    one_d = arr.ndim == 1
    if one_d:
        arr = arr[None, :]
    n = arr.shape[1]
    out = np.full(arr.shape, np.nan)
    for i in range(n):
        max_lag = min(i, window - 1)
        # Ascending in time: weight (window - lag) pairs the full weight with
        # the oldest value, x[i - max_lag].
        weights = window - np.arange(max_lag + 1, dtype=float)
        vals = arr[:, i - max_lag:i + 1]
        valid = ~np.isnan(vals)
        wsum = (valid * weights).sum(axis=1)
        vsum = np.nansum(vals * weights, axis=1)
        with np.errstate(invalid="ignore"):
            out[:, i] = np.where(wsum > 0, vsum / wsum, np.nan)
    return out[0] if one_d else out


def compute_ir_area(config):
    """Geodesic IR area in km2 from the shapefile.

    Computed on a sphere of radius 6,371,010 m, matching sf::st_area with its
    s2 default (which is what the reference panel carries); the WGS84
    ellipsoid gives areas about 0.4 percent larger and does not match.

    :param config: parsed config dict.
    :return: DataFrame(hierid, area_km2).
    """
    shp = read_ir_shapes(config)
    geod = pyproj.Geod(a=6_371_010, f=0)
    areas = np.array([abs(geod.geometry_area_perimeter(geom)[0])
                      for geom in shp.geometry])
    return pd.DataFrame({"hierid": shp["hierid"], "area_km2": areas / 1e6})


def postprocess_panel(config, scen="SSP3", gdp_model="IIASA"):
    """Assemble and post-process the final IR panel.

    :param config: parsed config dict.
    :param scen: SSP scenario.
    :param gdp_model: GDP model, "OECD" or "IIASA".
    :return: DataFrame with the ir_combined data columns (hierid, iso3, year,
        gdppc, gdppc_raw, gdppc_raw0, gdp, pop, area_km2, pop_density,
        pop_wtd_density, pop0to4, pop5to64, pop65plus).
    """
    # Raw income (1990-2100), extended with empty 1981-1989.
    raw = build_income(config, scen, gdp_model)[
        ["hierid", "iso3", "year", "gdppc"]].rename(
        columns={"gdppc": "gdppc_raw"})
    ids = raw[["hierid", "iso3"]].drop_duplicates()
    pre = ids.merge(pd.DataFrame({"year": np.arange(1981, 1990)}),
                    how="cross")
    pre = pre.assign(gdppc_raw=np.nan)
    raw = pd.concat([pre[["hierid", "iso3", "year", "gdppc_raw"]], raw],
                    ignore_index=True)

    # Smoothed income: 1981-2015 imputed as each IR's 1990-2015 mean, 2016+
    # the Bartlett kernel over that series; missing set to 0.
    imp = (raw[raw["year"].between(1990, 2015)]
           .groupby("hierid")["gdppc_raw"].mean().rename("m").reset_index())
    ser = raw.merge(imp, on="hierid", how="left")
    ser["gser"] = np.where(ser["year"] <= 2015, ser["m"], ser["gdppc_raw"])
    wide = ser.pivot(index="hierid", columns="year", values="gser")
    wide = wide.sort_index(axis=1)
    smooth = pd.DataFrame(bartlett_smooth(wide.to_numpy()),
                          index=wide.index, columns=wide.columns)
    gsm = smooth.stack().rename("gsm").reset_index()
    ser = ser.merge(gsm, on=["hierid", "year"])
    ser["gdppc"] = np.where(ser["year"] >= 2016, ser["gsm"], ser["gser"])
    ser["gdppc"] = ser["gdppc"].fillna(0)
    ser["gdppc_raw0"] = np.where(
        ser["year"] >= 1990, ser["gdppc_raw"].fillna(0), ser["gdppc_raw"])

    pop = build_population(config, scen)[["hierid", "iso3", "year", "pop"]]
    coh = build_cohorts(config, scen)[
        ["hierid", "year", "pop0to4", "pop5to64", "pop65plus"]]
    area = compute_ir_area(config)
    pwd = pd.read_csv(config["paths"]["cache"] / "ir_pop_wtd_density.csv")
    pwd = pwd[pwd["year"] == config["aggregation"]["pop_weight_year"]][
        ["hierid", "pop_wtd_density"]]

    panel = (ser[["hierid", "iso3", "year", "gdppc", "gdppc_raw",
                  "gdppc_raw0"]]
             .merge(pop, on=["hierid", "iso3", "year"], how="left")
             .merge(coh, on=["hierid", "year"], how="left")
             .merge(area, on="hierid", how="left")
             .merge(pwd, on="hierid", how="left"))

    for col in ("pop", "pop_wtd_density", "pop0to4", "pop5to64", "pop65plus"):
        panel[col] = panel[col].fillna(0)
    panel["gdp"] = panel["gdppc"] * panel["pop"]
    panel["pop_density"] = np.where(
        panel["area_km2"] > 0, panel["pop"] / panel["area_km2"], 0)

    return panel.sort_values(["hierid", "year"],
                             ignore_index=True)[PANEL_COLS]
