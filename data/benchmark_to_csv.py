# Convert the benchmark Zarr store to a compressed long CSV that read_benchmark
# in R can load. Zarr has no dependable R reader, so the conversion happens once
# in Python and the result is cached.
#
# Usage: python benchmark_to_csv.py <zarr_path> <out_csv_gz>

import sys

import xarray as xr


def main(zarr_path, out_path):
    ds = xr.open_zarr(zarr_path)
    df = ds.to_dataframe().reset_index()
    df.to_csv(out_path, index=False, compression="gzip")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
