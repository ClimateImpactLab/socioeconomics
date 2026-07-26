"""Command line entry point: python -m irpanel <stage>.

One subcommand per pipeline stage, mirroring the R targets graph. Implemented
so far: check-io, income, population, and cohorts; the remaining build stages
arrive module by module and raise until then. Python outputs go under
data/output/py so nothing clobbers the R side.
"""

import argparse

import numpy as np
import pandas as pd

from . import (__version__, aggregate as aggregate_mod,
               cohorts as cohorts_mod, income as income_mod, io,
               population as population_mod, postprocess as postprocess_mod)
from .compare import pct_diff_stats, report
from .config import load_config

CACHE_FILES = ("ir_gdppc_kummu.csv", "ir_pop_ghs.csv",
               "ir_pop_wtd_density.csv", "ir_kummu_validation.csv")


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


def _write_output(config, result, name):
    """Write a stage result under data/output/py and report it."""
    out_dir = config["paths"]["output_py"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / name
    result.to_csv(out, index=False, na_rep="NA")
    print(f"{len(result):,} rows -> {out}")


def _validate(config, result, value, ref_value, min_year=None):
    """Compare one result column against a reference panel column, printing
    the summary stats and the worst offenders."""
    ref_path = config["paths"]["reference"] / config["inputs"]["reference"]
    if not ref_path.exists():
        print("reference panel not present, validation skipped")
        return
    ref = pd.read_csv(ref_path, usecols=["hierid", "year", ref_value])
    if min_year is not None:
        ref = ref[ref["year"] >= min_year]
    res = result[["hierid", "year", value]].copy()
    res[value] = res[value].fillna(0)
    stats = pct_diff_stats(res, ref, ["hierid", "year"], value, ref_value)
    print(report(stats, f"{value} vs reference {ref_value}"))

    ref = ref.rename(columns={ref_value: "reference"})
    merged = res.merge(ref, on=["hierid", "year"])
    with np.errstate(divide="ignore", invalid="ignore"):
        merged["pct"] = (np.abs(merged[value] - merged["reference"])
                         / np.abs(merged["reference"]) * 100)
    worst = merged.nlargest(5, "pct")[
        ["hierid", "year", value, "reference", "pct"]]
    print("worst offenders:")
    print(worst.to_string(index=False))


def run_income(config):
    """Build income on the shared cache, write it, and validate the raw
    income against the reference panel's gdppc_raw0."""
    scen = config["run"]["scenario"]
    gdp_model = config["run"]["gdp_model"]
    result = income_mod.build_income(config, scen, gdp_model)
    _write_output(config, result, f"ir_income_{scen}_{gdp_model}.csv")
    _validate(config, result, "gdppc", "gdppc_raw0", min_year=1990)


def run_population(config):
    """Build population, write it, and validate against the reference pop."""
    scen = config["run"]["scenario"]
    result = population_mod.build_population(config, scen)
    _write_output(config, result, f"ir_population_{scen}.csv")
    _validate(config, result, "pop", "pop")


def run_cohorts(config):
    """Build cohorts, write them, and validate the three cohort columns."""
    scen = config["run"]["scenario"]
    result = cohorts_mod.build_cohorts(config, scen)
    _write_output(config, result, f"ir_cohorts_{scen}.csv")
    for col in ("pop0to4", "pop5to64", "pop65plus"):
        _validate(config, result, col, col)


def run_postprocess(config):
    """Assemble the full panel, write it, and validate every data column."""
    scen = config["run"]["scenario"]
    gdp_model = config["run"]["gdp_model"]
    result = postprocess_mod.postprocess_panel(config, scen, gdp_model)
    _write_output(config, result, f"ir_combined_{scen}_{gdp_model}.csv")
    for col in postprocess_mod.PANEL_COLS[3:]:
        _validate(config, result, col, col)


def run_aggregate(config):
    """Run the raster aggregation into the Python cache, then compare each
    cache CSV against the R cache when it is present."""
    kummu = io.read_kummu(config)
    ir_shapes = io.read_ir_shapes(config)
    aggregate_mod.aggregate_kummu_to_ir(kummu, ir_shapes, config)

    r_cache = config["paths"]["cache"]
    py_cache = config["paths"]["cache_py"]
    if not all((r_cache / f).exists() for f in CACHE_FILES):
        print("R cache not present, cache-to-cache comparison skipped")
        return
    print("\ncache-to-cache vs R:")
    for fname in CACHE_FILES:
        r = pd.read_csv(r_cache / fname)
        py = pd.read_csv(py_cache / fname)
        keys = [k for k in ("hierid", "iso3", "year") if k in r.columns]
        m = py.merge(r, on=keys, suffixes=("_py", "_r"), how="outer",
                     indicator=True)
        unmatched = int((m["_merge"] != "both").sum())
        vals = [c[:-3] for c in m.columns
                if c.endswith("_py") and m[c].dtype.kind == "f"]
        worst = 0.0
        for col in vals:
            a = m[f"{col}_py"].to_numpy(dtype=float)
            b = m[f"{col}_r"].to_numpy(dtype=float)
            with np.errstate(divide="ignore", invalid="ignore"):
                pct = np.abs(a - b) / np.abs(b) * 100
            pct[(b == 0) & (a == 0)] = 0.0
            pct[np.isnan(a) & np.isnan(b)] = 0.0
            worst = max(worst, np.nanmax(pct))
        print(f"  {fname}: unmatched {unmatched}, max |%diff| {worst:.3g}")


def run_all(config):
    """End to end on the Python cache: aggregate (unless already present),
    then the full chain reading the Python cache, validated per column."""
    py_cache = config["paths"]["cache_py"]
    if not all((py_cache / f).exists() for f in CACHE_FILES):
        run_aggregate(config)
    chain_config = {**config,
                    "paths": {**config["paths"], "cache": py_cache}}
    run_postprocess(chain_config)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="irpanel", description="IR socioeconomic panel pipeline (Python)")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="stage", required=True)
    sub.add_parser("check-io", help="read every input and report row counts")
    sub.add_parser("income", help="build income and validate vs reference")
    sub.add_parser("population",
                   help="build population and validate vs reference")
    sub.add_parser("cohorts", help="build cohorts and validate vs reference")
    sub.add_parser("postprocess",
                   help="assemble the panel and validate vs reference")
    sub.add_parser("aggregate",
                   help="raster aggregation into the Python cache")
    sub.add_parser("all", help="aggregate + full chain on the Python cache")
    args = parser.parse_args(argv)

    config = load_config()
    runners = {"check-io": check_io, "income": run_income,
               "population": run_population, "cohorts": run_cohorts,
               "postprocess": run_postprocess, "aggregate": run_aggregate,
               "all": run_all}
    runners[args.stage](config)


if __name__ == "__main__":
    main()
