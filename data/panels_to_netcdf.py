# Assemble the scenario x model panel CSVs into one self-contained NetCDF:
# dims (ssp, region, model, year) like the Zarr store, the metadata file
# that sits next to the CSVs stamped as global attributes, and the data
# dictionary's descriptions and units on every variable and coordinate.
# The writing happens in Python (xarray + netCDF4), as with
# panels_to_zarr.py.
#
# Usage: python panels_to_netcdf.py <out_nc> <header_yml> <dictionary_yml>
#        <panel_csv> [<panel_csv> ...]
# Each CSV must be named ir_combined_<scenario>_<model>.csv.

import os
import re
import sys

import numpy as np
import pandas as pd
import xarray as xr
import yaml

MODEL_LABELS = {"IIASA": "IIASA GDP", "OECD": "OECD Env-Growth"}
DATA_VARS = ["gdppc", "gdppc_raw", "gdppc_raw0", "gdp", "pop", "area_km2",
             "pop_density", "pop_wtd_density", "pop0to4", "pop5to64",
             "pop65plus"]
# Dictionary key block per NetCDF coordinate.
COORD_KEYS = {"ssp": "scenario", "region": "hierid", "model": "model",
              "year": "year"}


def read_panel(path):
    # keep_default_na=False so no region ID can be eaten by NA parsing;
    # empty strings (R's NA) still become NaN in the numeric columns.
    df = pd.read_csv(path, keep_default_na=False, na_values=[""])
    if (df["hierid"] == "").any() or df["hierid"].isna().any():
        sys.exit(f"{path}: empty region IDs — truncated or corrupt CSV")
    return df


def attr_value(value):
    """NetCDF attributes are scalars or strings; flatten anything nested."""
    if isinstance(value, (str, int, float)):
        return value
    if isinstance(value, bool):
        return str(value)
    return yaml.safe_dump(value, default_flow_style=True).strip()


def main(out_path, header_path, dict_path, csv_paths):
    with open(header_path) as fh:
        header = yaml.safe_load(fh)
    with open(dict_path) as fh:
        dictionary = yaml.safe_load(fh)

    frames = {}
    for path in csv_paths:
        m = re.search(r"ir_combined_(SSP\d)_([A-Za-z]+)\.csv(\.gz)?$", path)
        if not m:
            sys.exit(f"unrecognized panel filename: {path}")
        frames[(m.group(1), MODEL_LABELS[m.group(2)])] = read_panel(path)

    ssps = sorted({k[0] for k in frames})
    models = sorted({k[1] for k in frames})
    first = next(iter(frames.values()))
    regions = np.sort(first["hierid"].unique().astype(object))
    years = np.sort(first["year"].unique()).astype("int64")
    assert (np.diff(years) == 1).all(), "years must be contiguous"

    shape = (len(ssps), len(regions), len(models), len(years))
    data = {v: np.full(shape, np.nan, dtype="float32") for v in DATA_VARS}
    for (sc, gm), df in frames.items():
        i, k = ssps.index(sc), models.index(gm)
        if len(df) != len(regions) * len(years):
            sys.exit(f"{sc}/{gm}: {len(df)} rows, expected "
                     f"{len(regions) * len(years)} — truncated CSV")
        r_idx = pd.Categorical(df["hierid"], categories=regions).codes
        y_idx = df["year"].to_numpy() - years[0]
        if (r_idx < 0).any():
            sys.exit(f"{sc}/{gm}: region IDs not in the first panel")
        for v in DATA_VARS:
            data[v][i, r_idx, k, y_idx] = df[v].to_numpy(dtype="float32")

    ds = xr.Dataset(
        {v: (("ssp", "region", "model", "year"), data[v])
         for v in DATA_VARS},
        coords={"ssp": np.array(ssps, dtype="U4"),
                "region": regions,
                "model": np.array(models, dtype=object),
                "year": years},
    )

    # Global attributes: everything in the metadata file except the column
    # blocks, which become per-variable attributes instead.
    for key, value in header.items():
        if key == "variables":
            continue
        ds.attrs[key] = attr_value(value)
    columns = header.get("variables", {})
    for v in DATA_VARS:
        block = columns.get(v, dictionary.get("variables", {}).get(v, {}))
        if block.get("description"):
            ds[v].attrs["long_name"] = " ".join(
                str(block["description"]).split())
        if block.get("unit"):
            ds[v].attrs["units"] = str(block["unit"])
    for coord, key in COORD_KEYS.items():
        block = columns.get(key, dictionary.get("keys", {}).get(key, {}))
        if block.get("description"):
            ds[coord].attrs["long_name"] = " ".join(
                str(block["description"]).split())

    encoding = {v: {"zlib": True, "complevel": 4} for v in DATA_VARS}
    ds.to_netcdf(out_path, mode="w", engine="netcdf4", encoding=encoding)
    if not os.path.exists(out_path):
        sys.exit(f"{out_path}: not written")
    print(f"wrote {out_path}: "
          f"ssp {len(ssps)} x region {len(regions)} x model {len(models)} "
          f"x year {len(years)}, {len(DATA_VARS)} variables, "
          f"{os.path.getsize(out_path) / 1e6:.0f} MB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:])
