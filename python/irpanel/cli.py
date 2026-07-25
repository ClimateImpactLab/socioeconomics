"""Command line entry point: python -m irpanel <stage>.

One subcommand per pipeline stage, mirroring the R targets graph. Implemented
so far: check-io and income; the remaining build stages arrive module by
module and raise until then. Python outputs go under data/output/py so
nothing clobbers the R side.
"""

import argparse
import sys

import numpy as np
import pandas as pd

from . import __version__, income as income_mod, io
from .compare import pct_diff_stats, report
from .config import load_config

STAGES = ("aggregate", "population", "cohorts", "postprocess", "all")


def check_io(config):
    """Read every available input and print one line per reader."""
    pwt = io.read_pwt(config)
    print(f"pwt: {len(pwt):,} rows, {pwt['iso3'].nunique()} countries")
    ssp = io.read_ssp(config)
    for name, df in ssp.items():
        print(f"ssp {name}: {len(df):,} rows")
    kummu = io.read_kummu(config)
    print(f"kummu adm0: {len(kummu['adm0']):,} rows; rasters "
          f"{kummu['gdp_rast_path'].name}, {kummu['pop_rast_path'].name}")
    wpp = io.read_wpp(config)
    print(f"wpp: {len(wpp):,} rows, "
          f"years {wpp['year'].min()}-{wpp['year'].max()}")
    if config["paths"]["ir_shapes"].exists():
        shp = io.read_ir_shapes(config)
        print(f"ir_shapes: {len(shp)} polygons")
    else:
        print("ir_shapes: not reachable, skipped")


def run_income(config):
    """Build income on the shared cache, write it, and validate the raw
    income against the reference panel's gdppc_raw0."""
    scen = config["run"]["scenario"]
    gdp_model = config["run"]["gdp_model"]
    result = income_mod.build_income(config, scen, gdp_model)

    out_dir = config["paths"]["output_py"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"ir_income_{scen}_{gdp_model}.csv"
    result.to_csv(out, index=False)
    print(f"income: {len(result):,} rows -> {out}")

    ref_path = (config["paths"]["reference"]
                / config["inputs"]["reference"])
    if not ref_path.exists():
        print("reference panel not present, validation skipped")
        return
    ref = pd.read_csv(ref_path, usecols=["hierid", "year", "gdppc_raw0"])
    ref = ref[ref["year"] >= 1990]
    res = result[["hierid", "year", "gdppc"]].copy()
    res["gdppc"] = res["gdppc"].fillna(0)
    stats = pct_diff_stats(res, ref, ["hierid", "year"],
                           "gdppc", "gdppc_raw0")
    print(report(stats, "income vs reference gdppc_raw0"))

    merged = res.merge(ref, on=["hierid", "year"])
    with np.errstate(divide="ignore", invalid="ignore"):
        merged["pct"] = (np.abs(merged["gdppc"] - merged["gdppc_raw0"])
                         / np.abs(merged["gdppc_raw0"]) * 100)
    worst = merged.nlargest(5, "pct")[
        ["hierid", "year", "gdppc", "gdppc_raw0", "pct"]]
    print("worst offenders:")
    print(worst.to_string(index=False))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="irpanel", description="IR socioeconomic panel pipeline (Python)")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="stage", required=True)
    sub.add_parser("check-io", help="read every input and report row counts")
    sub.add_parser("income", help="build income and validate vs reference")
    for stage in STAGES:
        sub.add_parser(stage, help="not implemented yet")
    args = parser.parse_args(argv)

    config = load_config()
    if args.stage == "check-io":
        check_io(config)
    elif args.stage == "income":
        run_income(config)
    else:
        sys.exit(f"stage '{args.stage}' is not implemented yet")


if __name__ == "__main__":
    main()
