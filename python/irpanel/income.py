"""IR-level GDP per capita in 2005 PPP USD, mirroring R/income.R.

Historical years calibrate the Kummu subnational shape to the PWT national
level; projection years carry the 2023 level forward with SSP growth. Values
are in 2005 PPP throughout: PWT is deflated from 2021 and countries without
PWT use Kummu deflated from 2017.
"""

import numpy as np
import pandas as pd

from .io import read_kummu, read_pwt, read_ssp

# BEA GDP deflator (2017 = 100): 2005 = 81.556, 2021 = 110.186.
PWT_TO_2005 = 81.556 / 110.186
KUMMU_TO_2005 = 81.556 / 100


def interp_annual(df):
    """Log-linear interpolation of 5-year knots to annual, per iso3.

    :param df: DataFrame(iso3, year, gdppc) at 5-year (or mixed) knots.
    :return: DataFrame(iso3, year, gdppc) annual between each country's first
        and last knot. Countries with fewer than two knots are dropped.
    """
    df = df[df["gdppc"].notna() & (df["gdppc"] > 0)]
    parts = []
    for iso3, g in df.groupby("iso3"):
        if len(g) < 2:
            continue
        g = g.sort_values("year")
        years = np.arange(g["year"].min(), g["year"].max() + 1)
        vals = np.exp(np.interp(years, g["year"], np.log(g["gdppc"])))
        parts.append(pd.DataFrame({"iso3": iso3, "year": years, "gdppc": vals}))
    if not parts:
        return pd.DataFrame(columns=["iso3", "year", "gdppc"])
    return pd.concat(parts, ignore_index=True)


def ssp_growth(ssp_gdppc, gdp_model):
    """Growth relative to 2023 for the chosen GDP model, per iso3 x year
    (2024-2100).

    OECD is used directly. IIASA has no pre-2025 data, so its first two years
    are bridged with OECD growth and its own growth is chained from 2026.
    Countries with only IIASA use their 2025-2030 annualised rate for the
    first two years. Finally the missing model is cross-filled with the other
    (reference Step 3c): the IIASA panel uses OECD growth for OECD-only
    countries, and the OECD panel uses IIASA growth for IIASA-only countries.

    :param ssp_gdppc: DataFrame(model, scenario, iso3, year, gdppc), one
        scenario.
    :param gdp_model: "OECD" or "IIASA".
    :return: DataFrame(iso3, year, growth).
    """
    oecd = interp_annual(
        ssp_gdppc[ssp_gdppc["model"] == "OECD"][["iso3", "year", "gdppc"]])
    base = oecd[oecd["year"] == 2023][["iso3", "gdppc"]].rename(
        columns={"gdppc": "base"})
    oecd_g = oecd[oecd["year"] >= 2024].merge(base, on="iso3")
    oecd_g = oecd_g.assign(growth=oecd_g["gdppc"] / oecd_g["base"])[
        ["iso3", "year", "growth"]]

    iiasa = interp_annual(
        ssp_gdppc[ssp_gdppc["model"] == "IIASA"][["iso3", "year", "gdppc"]])
    b25 = iiasa[iiasa["year"] == 2025][["iso3", "gdppc"]].rename(
        columns={"gdppc": "b25"})
    from25 = iiasa[iiasa["year"] > 2025].merge(b25, on="iso3")
    from25 = from25.assign(gf=from25["gdppc"] / from25["b25"])
    g_o_25 = oecd_g[oecd_g["year"] == 2025][["iso3", "growth"]].rename(
        columns={"growth": "g25"})

    with_oecd = set(iiasa["iso3"]) & set(oecd_g["iso3"])
    bridge = oecd_g[oecd_g["year"].isin((2024, 2025))
                    & oecd_g["iso3"].isin(with_oecd)]
    chained = from25[from25["iso3"].isin(with_oecd)].merge(g_o_25, on="iso3")
    chained = chained.assign(growth=chained["g25"] * chained["gf"])[
        ["iso3", "year", "growth"]]
    iiasa_g = pd.concat([bridge, chained], ignore_index=True)

    only = set(iiasa["iso3"]) - set(oecd_g["iso3"])
    if only:
        a = iiasa[iiasa["iso3"].isin(only)]
        ann = a[a["year"] == 2030][["iso3", "gdppc"]].rename(
            columns={"gdppc": "g30"}).merge(
            a[a["year"] == 2025][["iso3", "gdppc"]].rename(
                columns={"gdppc": "g25"}), on="iso3")
        ann = ann.assign(gann=(ann["g30"] / ann["g25"]) ** (1 / 5))
        early = pd.concat([
            ann.assign(year=2024, growth=ann["gann"]),
            ann.assign(year=2025, growth=ann["gann"] ** 2),
        ])[["iso3", "year", "growth"]]
        g_only_25 = early[early["year"] == 2025][["iso3", "growth"]].rename(
            columns={"growth": "g25"})
        late = from25[from25["iso3"].isin(only)].merge(g_only_25, on="iso3")
        late = late.assign(growth=late["g25"] * late["gf"])[
            ["iso3", "year", "growth"]]
        iiasa_g = pd.concat([iiasa_g, early, late], ignore_index=True)

    oecd_iso = set(oecd_g["iso3"])
    iiasa_iso = set(iiasa_g["iso3"])
    if gdp_model == "IIASA":
        fill = oecd_g[oecd_g["iso3"].isin(oecd_iso - iiasa_iso)]
        return pd.concat([iiasa_g, fill], ignore_index=True)
    fill = iiasa_g[iiasa_g["iso3"].isin(iiasa_iso - oecd_iso)]
    return pd.concat([oecd_g, fill], ignore_index=True)


def venezuela_income(kummu_ir, adm0, pwt, ssp_gdppc):
    """Replace Venezuela's 2012-2023 national level, where PWT's chained PPP
    breaks, with a log-linear path from PWT 2011 to the IIASA 2025 level,
    keeping the Kummu subnational shares. Values in 2005 PPP.

    :param kummu_ir: DataFrame(hierid, iso3, year, kummu_ir).
    :param adm0: DataFrame(iso3, year, kummu_nat).
    :param pwt: DataFrame with iso3, year, pwt (2005 PPP).
    :param ssp_gdppc: DataFrame(model, scenario, iso3, year, gdppc).
    :return: DataFrame(hierid, iso3, year, gdppc) for 2012-2023, or None when
        the anchor levels are missing.
    """
    p = pwt.loc[(pwt["iso3"] == "VEN") & (pwt["year"] == 2011), "pwt"]
    s = ssp_gdppc.loc[(ssp_gdppc["model"] == "IIASA")
                      & (ssp_gdppc["iso3"] == "VEN")
                      & (ssp_gdppc["year"] == 2025), "gdppc"]
    s2025 = s.mean() * KUMMU_TO_2005 if len(s) else np.nan
    if len(p) != 1 or pd.isna(p.iloc[0]) or pd.isna(s2025):
        return None
    p2011 = p.iloc[0]
    years = np.arange(2012, 2024)
    nat = pd.DataFrame({
        "year": years,
        "nat": p2011 * np.exp(
            np.log(s2025 / p2011) * (years - 2011) / (2025 - 2011)),
    })
    k = kummu_ir[(kummu_ir["iso3"] == "VEN")
                 & kummu_ir["year"].between(2012, 2022)]
    k = k.merge(adm0.loc[adm0["iso3"] == "VEN",
                         ["iso3", "year", "kummu_nat"]], on=["iso3", "year"])
    k = k.merge(nat, on="year")
    k = k[k["kummu_ir"].notna() & (k["kummu_nat"] > 0)]
    k = k.assign(gdppc=k["kummu_ir"] / k["kummu_nat"] * k["nat"])[
        ["hierid", "iso3", "year", "gdppc"]]
    g = (nat.loc[nat["year"] == 2023, "nat"].iloc[0]
         / nat.loc[nat["year"] == 2022, "nat"].iloc[0])
    k23 = k[k["year"] == 2022].assign(year=2023)
    k23 = k23.assign(gdppc=k23["gdppc"] * g)
    return pd.concat([k, k23], ignore_index=True)


def build_income(config, scen="SSP3", gdp_model="IIASA"):
    """Build the IR-level GDP-per-capita panel in 2005 PPP USD.

    :param config: parsed config dict.
    :param scen: SSP scenario (projection growth).
    :param gdp_model: GDP model, "OECD" or "IIASA".
    :return: DataFrame(hierid, iso3, year, scenario, gdp_model, gdppc),
        1990-2100.
    """
    cache = config["paths"]["cache"]
    kummu_ir = pd.read_csv(cache / "ir_gdppc_kummu.csv").rename(
        columns={"gdppc": "kummu_ir"})
    pop_ghs = pd.read_csv(cache / "ir_pop_ghs.csv")
    wy = config["aggregation"]["pop_weight_year"]
    pop_base = pop_ghs[pop_ghs["year"] == wy][["hierid", "pop"]].rename(
        columns={"pop": "pop_base"})

    adm0 = read_kummu(config)["adm0"].rename(columns={"gdppc": "kummu_nat"})
    pwt = read_pwt(config)
    pwt = pwt.assign(pwt=pwt["gdppc"] * PWT_TO_2005)
    ssp_gdppc = read_ssp(config)["gdppc"]
    ssp_gdppc = ssp_gdppc[ssp_gdppc["scenario"] == scen]

    # Historical calibration, 1990-2022.
    h = kummu_ir[kummu_ir["year"].between(1990, 2022)][
        ["hierid", "iso3", "year", "kummu_ir"]]
    h = h.merge(adm0[["iso3", "year", "kummu_nat"]],
                on=["iso3", "year"], how="left")
    h = h.merge(pwt[["iso3", "year", "pwt"]], on=["iso3", "year"], how="left")
    h["gdppc"] = np.nan
    ok = (h["kummu_ir"].notna() & h["kummu_nat"].notna()
          & (h["kummu_nat"] > 0) & h["pwt"].notna())
    h.loc[ok, "gdppc"] = (h.loc[ok, "kummu_ir"] / h.loc[ok, "kummu_nat"]
                          * h.loc[ok, "pwt"])

    # Countries with no PWT at all: raw Kummu deflated 2017 -> 2005.
    has_iso = set(h.loc[h["gdppc"].notna(), "iso3"])
    all_iso = set(h.loc[h["kummu_ir"].notna(), "iso3"])
    no_pwt = all_iso - has_iso
    sel = h["iso3"].isin(no_pwt) & h["gdppc"].isna() & h["kummu_ir"].notna()
    h.loc[sel, "gdppc"] = h.loc[sel, "kummu_ir"] * KUMMU_TO_2005

    # IRs with no raster value: populated ones take a national fallback, the
    # rest stay NA (uninhabited).
    glob_pwt = (pwt[pwt["year"].between(1990, 2022)]
                .groupby("year")["pwt"].mean().rename("g_pwt").reset_index())
    fb = (h[h["kummu_ir"].isna()]
          .merge(pop_base, on="hierid", how="left")
          .merge(glob_pwt, on="year", how="left"))
    fb = fb[fb["pop_base"].notna() & (fb["pop_base"] > 0.5)]
    gval = np.where(fb["pwt"].notna(), fb["pwt"],
                    np.where(fb["kummu_nat"].notna(),
                             fb["kummu_nat"] * KUMMU_TO_2005, fb["g_pwt"]))
    upd = pd.Series(
        gval, index=pd.MultiIndex.from_arrays([fb["hierid"], fb["year"]]))
    h = h.set_index(["hierid", "year"])
    h.loc[upd.index, "gdppc"] = upd
    h = h.reset_index()

    hist = h[["hierid", "iso3", "year", "gdppc"]]

    # Year 2023: roll 2022 forward by PWT growth, then SSP-implied, then a
    # global-average SSP growth.
    pw = pwt[pwt["year"].isin((2022, 2023))].pivot(
        index="iso3", columns="year", values="pwt")
    pw = pw.dropna()
    pw = (pw.loc[pw[2022] > 0, 2023] / pw.loc[pw[2022] > 0, 2022]).rename(
        "g_pwt").reset_index()
    oecd_ann = interp_annual(
        ssp_gdppc[ssp_gdppc["model"] == "OECD"][["iso3", "year", "gdppc"]])
    os = oecd_ann[oecd_ann["year"].isin((2022, 2023))].pivot(
        index="iso3", columns="year", values="gdppc")
    os = os.dropna()
    os = (os.loc[os[2022] > 0, 2023] / os.loc[os[2022] > 0, 2022]).rename(
        "g_ssp").reset_index()
    glob_g = np.exp(np.log(os["g_ssp"]).mean())
    y23 = (hist[hist["year"] == 2022]
           .merge(pw, on="iso3", how="left")
           .merge(os, on="iso3", how="left"))
    y23["g"] = y23["g_pwt"].fillna(y23["g_ssp"]).fillna(glob_g)
    y23 = y23.assign(year=2023, gdppc=y23["gdppc"] * y23["g"])[
        ["hierid", "iso3", "year", "gdppc"]]
    baseline = pd.concat([hist, y23], ignore_index=True)

    # Venezuela: replace 2012-2023 with the interpolated national level.
    ven = venezuela_income(kummu_ir, adm0, pwt, ssp_gdppc)
    if ven is not None:
        baseline = baseline[~((baseline["iso3"] == "VEN")
                              & (baseline["year"] >= 2012))]
        baseline = pd.concat([baseline, ven], ignore_index=True)

    # Projections 2024-2100: 2023 level times SSP growth, with a
    # global-average growth fallback for countries the SSP does not cover.
    growth = ssp_growth(ssp_gdppc, gdp_model)
    glob_growth = (growth.groupby("year")["growth"]
                   .apply(lambda s: np.exp(np.log(s).mean()))
                   .rename("growth").reset_index())
    base23 = baseline[baseline["year"] == 2023][
        ["hierid", "iso3", "gdppc"]].rename(columns={"gdppc": "gdppc_2023"})
    need = sorted(set(base23["iso3"]) - set(growth["iso3"]))
    if need:
        growth = pd.concat(
            [growth] + [glob_growth.assign(iso3=i) for i in need],
            ignore_index=True)
    proj = base23.merge(growth, on="iso3")
    proj = proj.assign(gdppc=proj["gdppc_2023"] * proj["growth"])[
        ["hierid", "iso3", "year", "gdppc"]]

    income = pd.concat([baseline, proj], ignore_index=True)

    # Delta #2 (force_gdp_sum) insertion point. In reproduction mode this is
    # off; when enabled, rescale each country's IR gdppc here so
    # sum_IR(gdppc * pop) matches national GDP within tolerances gdp_sum_pct.
    if config["deltas"].get("force_gdp_sum"):
        raise NotImplementedError("force_gdp_sum is not implemented yet")

    income = income.assign(scenario=scen, gdp_model=gdp_model)
    return income.sort_values(["hierid", "year"], ignore_index=True)[
        ["hierid", "iso3", "year", "scenario", "gdp_model", "gdppc"]]
