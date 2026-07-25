"""Command line entry point: python -m irpanel <stage>.

One subcommand per pipeline stage, mirroring the R targets graph. Only
check-io is implemented so far; the build stages arrive module by module and
raise until then. Python outputs go under data/output/py so nothing clobbers
the R side.
"""

import argparse
import sys

from . import __version__, io
from .config import load_config

STAGES = ("aggregate", "income", "population", "cohorts", "postprocess", "all")


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


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="irpanel", description="IR socioeconomic panel pipeline (Python)")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="stage", required=True)
    sub.add_parser("check-io", help="read every input and report row counts")
    for stage in STAGES:
        sub.add_parser(stage, help="not implemented yet")
    args = parser.parse_args(argv)

    config = load_config()
    if args.stage == "check-io":
        check_io(config)
    else:
        sys.exit(f"stage '{args.stage}' is not implemented yet")


if __name__ == "__main__":
    main()
