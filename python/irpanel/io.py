"""Input readers: one function per raw source, mirroring R/io.R.

Each reader returns a tidy DataFrame (or a dict of them) for the pipeline.
Paths resolve from the shared config; ir_shapes is a read-only absolute path
on the shared volume.
"""

import logging
import re

import country_converter
import geopandas as gpd
import numpy as np
import pandas as pd

# country_converter logs a warning per unmatched name; the unmapped regions
# are collected and reported once instead, as the R reader does.
logging.getLogger("country_converter").setLevel(logging.ERROR)

_converter = country_converter.CountryConverter()


def read_pwt(config):
    """Read Penn World Table 11.0 national GDP per capita (rgdpe / pop).

    :param config: parsed config dict.
    :return: DataFrame(iso3, year, gdppc). PWT already carries ISO3 codes.
    """
    path = config["paths"]["source"] / config["inputs"]["pwt"]
    d = pd.read_excel(path, sheet_name="Data")
    d = d[d["rgdpe"].notna() & d["pop"].notna() & (d["pop"] > 0)]
    out = pd.DataFrame({
        "iso3": d["countrycode"],
        "year": d["year"].astype(int),
        "gdppc": d["rgdpe"] / d["pop"],
    })
    return out.dropna(subset=["iso3"]).sort_values(
        ["iso3", "year"], ignore_index=True)


def _regions_to_iso3(df):
    """Map SSP region names to ISO3, dropping aggregates and unresolved names.

    Aggregates are "World" and the "(R5)"/"(R9)"/"(R10)" suffixed groups; some
    real countries also carry parentheses, so only that suffix is dropped.
    Kosovo, Taiwan, and Micronesia are fixed by hand; Curacao and Reunion are
    matched by prefix so both accented and plain spellings resolve.
    """
    df = df[(df["region"] != "World")
            & ~df["region"].str.contains(r"\(R[0-9]+\)$", regex=True)]
    regions = df["region"].unique()
    exact = {"Kosovo": "XKX", "Taiwan": "TWN", "Micronesia": "FSM"}
    lut = {}
    for reg in regions:
        if reg in exact:
            lut[reg] = exact[reg]
        elif reg.startswith("Cura"):
            lut[reg] = "CUW"
        elif re.fullmatch(r"R.union", reg):
            lut[reg] = "REU"
    need = [r for r in regions if r not in lut]
    mapped = _converter.convert(need, to="ISO3", not_found=None)
    if isinstance(mapped, str):
        mapped = [mapped]
    lut.update({r: m for r, m in zip(need, mapped) if m})
    unmapped = sorted(set(regions) - set(lut))
    if unmapped:
        print(f"read_ssp: dropping {len(unmapped)} unmapped region(s): "
              + ", ".join(unmapped))
    out = df.copy()
    out["iso3"] = out["region"].map(lut)
    return out.dropna(subset=["iso3"])


def _age_bins(df, era):
    """Sum male+female population into 0-4 / 5-64 / 65+ per scenario/iso/year.

    Only the two-pipe "Population|<sex>|Age <bin>" variables are used, which
    excludes the education splits and "Mean Years of Education".
    """
    a = df[df["variable"].str.fullmatch(
        r"Population\|(Male|Female)\|Age [^|]+")].copy()
    lower = a["variable"].str.extract(r"\|Age (\d+)")[0].astype(int)
    a["bin"] = np.where(lower < 5, "age0to4",
                        np.where(lower < 65, "age5to64", "age65plus"))
    wide = (a.groupby(["scenario", "iso3", "year", "bin"])["value"].sum()
             .unstack("bin", fill_value=0).reset_index())
    for col in ("age0to4", "age5to64", "age65plus"):
        if col not in wide.columns:
            wide[col] = 0.0
    wide.insert(0, "era", era)
    return wide[["era", "scenario", "iso3", "year",
                 "age0to4", "age5to64", "age65plus"]]


def _wide_to_long(wide):
    """Melt a wide SSP table (five id columns then year columns) to long form
    keyed on iso3, dropping the copyright footer row if present."""
    id_cols = ["model", "scenario", "region", "variable", "unit"]
    wide = wide.rename(columns=dict(zip(wide.columns[:5], id_cols)))
    wide = wide[~wide["model"].astype(str).str.startswith("©")]
    year_cols = [c for c in wide.columns if re.fullmatch(r"[0-9]{4}", str(c))]
    long = wide.melt(id_vars=id_cols, value_vars=year_cols,
                     var_name="year", value_name="value")
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long = long.dropna(subset=["value"])
    long["year"] = long["year"].astype(int)
    return _regions_to_iso3(long)


def _read_snapshot(path):
    """Read a wide SSP snapshot CSV. The files carry a byte-order mark; if the
    header still ends up in the first data row, recover it."""
    d = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    if "Model" not in d.columns:
        d.columns = d.iloc[0]
        d = d.iloc[1:].reset_index(drop=True)
    return d


def read_ssp(config):
    """Read national SSP GDP, population, and age cohorts, keyed on ISO3.

    The SSP release 3.1 data comes from snapshot CSVs: one or several
    projection files (2020-2100, together covering the run's scenarios) and
    one history file (1950-2020).

    :param config: parsed config dict.
    :return: dict with three DataFrames: gdppc (model, scenario, iso3, year,
        gdppc in 2017 PPP USD), pop (era, scenario, iso3, year, pop in
        millions), cohorts (era, scenario, iso3, year, age0to4, age5to64,
        age65plus in millions). era is "historical" or "projection".
    """
    src = config["paths"]["source"]
    proj_files = config["inputs"]["ssp_snap_proj"]
    if isinstance(proj_files, str):
        proj_files = [proj_files]
    proj = pd.concat(
        [_wide_to_long(_read_snapshot(src / f)) for f in proj_files],
        ignore_index=True)
    # A repeated model/scenario row would silently double-count downstream.
    dup = proj.duplicated(["model", "scenario", "region", "variable", "year"])
    if dup.any():
        raise ValueError("read_ssp: duplicate model/scenario rows across "
                         "the projection snapshots")
    hist = _wide_to_long(
        _read_snapshot(src / config["inputs"]["ssp_snap_hist"]))

    # GDP per capita. OECD gives it directly; IIASA gives total GDP only, so
    # its per capita is total GDP divided by the IIASA-WiC POP 2023 population
    # from the same release (billion / million * 1e3 -> USD per person).
    oecd = proj[(proj["model"] == "OECD ENV-Growth 2023")
                & (proj["variable"] == "GDP|PPP [per capita]")]
    oecd = oecd.assign(model="OECD", gdppc=oecd["value"])[
        ["model", "scenario", "iso3", "year", "gdppc"]]
    iiasa_gdp = proj[(proj["model"] == "IIASA GDP 2023")
                     & (proj["variable"] == "GDP|PPP")][
        ["scenario", "iso3", "year", "value"]].rename(
        columns={"value": "gdp_bn"})
    iiasa_pop = proj[(proj["model"] == "IIASA-WiC POP 2023")
                     & (proj["variable"] == "Population")][
        ["scenario", "iso3", "year", "value"]].rename(
        columns={"value": "pop_mn"})
    iiasa = iiasa_gdp.merge(iiasa_pop, on=["scenario", "iso3", "year"])
    iiasa = iiasa[iiasa["pop_mn"] > 0]
    iiasa = iiasa.assign(model="IIASA",
                         gdppc=iiasa["gdp_bn"] / iiasa["pop_mn"] * 1e3)[
        ["model", "scenario", "iso3", "year", "gdppc"]]
    gdppc = pd.concat([oecd, iiasa], ignore_index=True)

    # National population, both eras (millions).
    pop_proj = proj[(proj["model"] == "IIASA-WiC POP 2023")
                    & (proj["variable"] == "Population")]
    pop_proj = pop_proj.assign(era="projection", pop=pop_proj["value"])[
        ["era", "scenario", "iso3", "year", "pop"]]
    pop_hist = hist[hist["variable"] == "Population"]
    pop_hist = pop_hist.assign(era="historical", pop=pop_hist["value"])[
        ["era", "scenario", "iso3", "year", "pop"]]
    pop = pd.concat([pop_hist, pop_proj], ignore_index=True)

    # Age cohorts, both eras (millions).
    cohorts = pd.concat([
        _age_bins(hist, "historical"),
        _age_bins(proj[proj["model"] == "IIASA-WiC POP 2023"], "projection"),
    ], ignore_index=True)

    return {
        "gdppc": gdppc.sort_values(["model", "scenario", "iso3", "year"],
                                   ignore_index=True),
        "pop": pop.sort_values(["era", "scenario", "iso3", "year"],
                               ignore_index=True),
        "cohorts": cohorts.sort_values(["era", "scenario", "iso3", "year"],
                                       ignore_index=True),
    }


def read_kummu(config):
    """Read Kummu et al. (2025) national GDP per capita and the raster paths.

    :param config: parsed config dict.
    :return: dict with adm0 (DataFrame iso3, year, gdppc) and gdp_rast_path /
        pop_rast_path (Paths; the rasters are not loaded here).
    """
    src = config["paths"]["source"]
    wide = pd.read_csv(src / config["inputs"]["kummu_adm0"])
    year_cols = [c for c in wide.columns if re.fullmatch(r"[0-9]{4}", str(c))]
    adm0 = wide.melt(id_vars=["iso3"], value_vars=year_cols,
                     var_name="year", value_name="gdppc")
    adm0["year"] = adm0["year"].astype(int)
    adm0 = adm0[adm0["iso3"].notna() & (adm0["iso3"] != "")
                & adm0["gdppc"].notna()]
    return {
        "adm0": adm0.sort_values(["iso3", "year"], ignore_index=True),
        "gdp_rast_path": (src / config["inputs"]["kummu_gdp_rast"]).resolve(),
        "pop_rast_path": (src / config["inputs"]["kummu_pop_rast"]).resolve(),
    }


def _read_wpp_sheet(path, sheet):
    """Read one WPP sheet (Estimates or Medium variant). The data starts a few
    rows below a header block, so the header row is found by its "ISO3
    Alpha-code" label rather than a fixed offset. Country rows are Type
    "Country/Area"; regional groupings and the World total are dropped.
    Population is the mid-year (1 July) total, thousands to millions."""
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    hdr = (raw == "ISO3 Alpha-code").any(axis=1).idxmax()
    header = raw.iloc[hdr].astype(str)
    col = {label: header[header == label].index[0] for label in (
        "ISO3 Alpha-code", "Type", "Year",
        "Total Population, as of 1 July (thousands)")}
    body = raw.iloc[hdr + 1:]
    out = pd.DataFrame({
        "iso3": body[col["ISO3 Alpha-code"]].astype(str),
        "type": body[col["Type"]].astype(str),
        "year": pd.to_numeric(body[col["Year"]], errors="coerce"),
        "pop": pd.to_numeric(
            body[col["Total Population, as of 1 July (thousands)"]],
            errors="coerce") / 1e3,
    })
    out = out[(out["type"] == "Country/Area")
              & (out["iso3"] != "nan") & out["year"].notna()]
    out["year"] = out["year"].astype(int)
    return out[["iso3", "year", "pop"]]


def read_wpp(config):
    """Read UN WPP 2024 national population totals, keyed on ISO3 (millions).

    :param config: parsed config dict.
    :return: DataFrame(iso3, year, pop) over estimates and the medium variant.
    """
    path = config["paths"]["source"] / config["inputs"]["wpp"]
    both = pd.concat([
        _read_wpp_sheet(path, "Estimates"),
        _read_wpp_sheet(path, "Medium variant"),
    ], ignore_index=True)
    # Estimates end at 2023 and the medium variant begins at 2024; keep the
    # estimate if any year appears in both.
    both = both.sort_values(["iso3", "year"], kind="stable")
    return both.drop_duplicates(["iso3", "year"], keep="first",
                                ignore_index=True)


def read_ir_shapes(config):
    """Read the impact-region polygons, assigning WGS84 if the CRS is missing.

    Feature order matters: the aggregation writes extract results in polygon
    order. pyogrio reads shapefile features in file order, the same order
    sf::st_read gives the R side. Geometry cleaning uses GEOS make_valid;
    the R side cleans through s2 (sf's st_make_valid for geographic
    coordinates), and the two libraries resolve degenerate rings differently
    on a documented set of impact regions — see docs/python-reproduction.md.

    :param config: parsed config dict.
    :return: GeoDataFrame keyed on hierid.
    """
    shp = gpd.read_file(config["paths"]["ir_shapes"])
    if shp.crs is None:
        shp = shp.set_crs(4326)
    shp.geometry = shp.geometry.make_valid()
    print(f"read_ir_shapes: {len(shp)} polygons")
    return shp
