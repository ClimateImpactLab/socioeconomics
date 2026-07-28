# Assemble the scenario x model panel CSVs into one Zarr store mirroring the
# benchmark layout (integration-econ-bc39.zarr): dims (ssp, region, model,
# year), float32 data variables, model labels "IIASA GDP" / "OECD Env-Growth",
# blosc/lz4 compression, consolidated metadata. Zarr has no dependable R
# writer, so the serialization happens in Python, as with benchmark_to_csv.py.
#
# Usage: python panels_to_zarr.py <out_zarr> <panel_csv> [<panel_csv> ...]
# Each CSV must be named ir_combined_<scenario>_<model>.csv.

import os
import re
import sys

import numpy as np
import pandas as pd
import xarray as xr
import zarr

MODEL_LABELS = {"IIASA": "IIASA GDP", "OECD": "OECD Env-Growth"}
DATA_VARS = ["gdppc", "gdppc_raw", "gdppc_raw0", "gdp", "pop", "area_km2",
             "pop_density", "pop_wtd_density", "pop0to4", "pop5to64",
             "pop65plus"]


def read_panel(path):
    # keep_default_na=False so no region ID can be eaten by NA parsing;
    # empty strings (R's NA) still become NaN in the numeric columns.
    df = pd.read_csv(path, keep_default_na=False, na_values=[""])
    if (df["hierid"] == "").any() or df["hierid"].isna().any():
        sys.exit(f"{path}: empty region IDs — truncated or corrupt CSV")
    return df


def main(out_path, csv_paths):
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
    chunks = (len(ssps), 6095, 1, 23)  # the benchmark's chunk scheme
    encoding = {v: {"chunks": chunks} for v in DATA_VARS}
    # The store must be Zarr V2 to stay a drop-in for readers of the bc39
    # benchmark. zarr 2.x only writes V2; zarr 3.x defaults to V3 and needs
    # the explicit format argument.
    kwargs = {}
    if int(zarr.__version__.split(".")[0]) >= 3:
        kwargs["zarr_format"] = 2
    ds.to_zarr(out_path, mode="w", encoding=encoding, consolidated=True,
               **kwargs)
    if not os.path.exists(os.path.join(out_path, ".zgroup")):
        sys.exit(f"{out_path}: not a Zarr V2 store (.zgroup missing) — "
                 f"written with zarr {zarr.__version__}")
    print(f"wrote {out_path} (zarr V2): "
          f"ssp {len(ssps)} x region {len(regions)} x model {len(models)} "
          f"x year {len(years)}, {len(DATA_VARS)} variables")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
