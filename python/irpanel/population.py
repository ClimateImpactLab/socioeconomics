"""IR-level population, mirroring R/population.R.

National totals are distributed across IRs by GHS-POP shares: fixed 2020
shares for the projection (2020-2100), year-specific shares for history
(1981-2019, frozen at 1990 before that). National control totals come from
the SSP population model (pop_control IIASA, the reproduction) or, with
pop_control UN_WPP, from UN WPP 2024 through the handoff year and from the
SSP scenario trajectory, rebased to the WPP handoff level, afterwards.
Interpolation of the national knots is linear (income uses log-linear;
population does not).
"""

import numpy as np
import pandas as pd

from .io import read_ssp, read_wpp


def pop_linear_annual(df):
    """Linear interpolation of national population knots to annual, per iso3.

    :param df: DataFrame(iso3, year, ssp_nat) at 5-year (or mixed) knots.
    :return: DataFrame(iso3, year, ssp_nat) annual between each country's
        first and last knot. Countries with fewer than two knots are dropped.
    """
    df = df[df["ssp_nat"].notna() & (df["ssp_nat"] > 0)]
    parts = []
    for iso3, g in df.groupby("iso3"):
        if len(g) < 2:
            continue
        g = g.sort_values("year")
        years = np.arange(g["year"].min(), g["year"].max() + 1)
        vals = np.interp(years, g["year"], g["ssp_nat"])
        parts.append(
            pd.DataFrame({"iso3": iso3, "year": years, "ssp_nat": vals}))
    if not parts:
        return pd.DataFrame(columns=["iso3", "year", "ssp_nat"])
    return pd.concat(parts, ignore_index=True)


def pop_handoff_year(config):
    """Handoff year for the UN_WPP control (deltas pop_handoff_year, default
    2023): the last year national totals follow UN WPP.

    :param config: parsed config dict.
    :return: the handoff year as int.
    """
    h = int(config["deltas"].get("pop_handoff_year", 2023))
    if h < 2020 or h > 2099:
        raise ValueError(
            "pop_handoff_year must be between 2020 and 2099, got %d" % h)
    return h


def wpp_ssp_projection_controls(config, scen):
    """Projection-era national controls (millions, annual, 2020-2100) for
    pop_control UN_WPP, mirroring R.

    UN WPP through the handoff year H, then the scenario's SSP trajectory
    rebased to the WPP level at H -- nat(t) = WPP(H) * SSP(t) / SSP(H) -- so
    the national path is continuous at H and scenarios diverge from H+1.
    Fallbacks: a country absent from the SSP scenario (or with a zero or
    missing anchor) stays on UN WPP in every year; a country absent from UN
    WPP gets no control here and keeps the frozen-GHS fallback in
    build_population.

    :param config: parsed config dict.
    :param scen: SSP scenario for the years after the handoff.
    :return: DataFrame(iso3, year, ssp_nat).
    """
    h = pop_handoff_year(config)
    wpp = read_wpp(config)
    proj = read_ssp(config)["pop"]
    proj = proj[(proj["era"] == "projection") & (proj["scenario"] == scen)]
    ssp_ann = pop_linear_annual(
        proj[["iso3", "year", "pop"]].rename(columns={"pop": "ssp_nat"}))
    sh = ssp_ann[(ssp_ann["year"] == h) & (ssp_ann["ssp_nat"] > 0)][
        ["iso3", "ssp_nat"]].rename(columns={"ssp_nat": "ssp_h"})
    wh = wpp[(wpp["year"] == h) & (wpp["pop"] > 0)][
        ["iso3", "pop"]].rename(columns={"pop": "wpp_h"})
    anchor = sh.merge(wh, on="iso3")
    resc = ssp_ann[ssp_ann["year"] > h].merge(anchor, on="iso3")
    resc = resc.assign(
        ssp_nat=resc["wpp_h"] * resc["ssp_nat"] / resc["ssp_h"])[
        ["iso3", "year", "ssp_nat"]]
    in_anchor = wpp["iso3"].isin(anchor["iso3"])
    pre = wpp[(wpp["year"] >= 2020) & (wpp["year"] <= h) & in_anchor][
        ["iso3", "year", "pop"]].rename(columns={"pop": "ssp_nat"})
    only = wpp[(wpp["year"] >= 2020) & ~in_anchor][
        ["iso3", "year", "pop"]].rename(columns={"pop": "ssp_nat"})
    return pop_linear_annual(
        pd.concat([pre, resc, only], ignore_index=True))


def build_population(config, scen="SSP3"):
    """Build the IR-level population panel (1981-2100) in persons.

    :param config: parsed config dict.
    :param scen: SSP scenario for the projection national totals.
    :return: DataFrame(hierid, iso3, year, scenario, pop).
    """
    # Delta #1 (pop_control): the national control totals, in millions.
    # "IIASA" scales to the SSP model totals in every year (the
    # reproduction); "UN_WPP" scales to UN WPP 2024 through the handoff
    # year, then to the SSP scenario trajectory rebased to the WPP handoff
    # level. The GHS shares and era logic are shared.
    pc = config["deltas"]["pop_control"]
    if pc not in ("IIASA", "UN_WPP"):
        raise ValueError("build_population: unknown pop_control %r" % pc)

    ghs = pd.read_csv(config["paths"]["cache"] / "ir_pop_ghs.csv")
    wy = config["aggregation"]["pop_weight_year"]

    if pc == "IIASA":
        ssp_pop = read_ssp(config)["pop"]
        proj_src = ssp_pop[(ssp_pop["era"] == "projection")
                           & (ssp_pop["scenario"] == scen)]
        proj_nat = pop_linear_annual(
            proj_src[["iso3", "year", "pop"]].rename(
                columns={"pop": "ssp_nat"}))
        hist_src = ssp_pop[ssp_pop["era"] == "historical"]
        hist_nat = pop_linear_annual(
            hist_src[["iso3", "year", "pop"]].rename(
                columns={"pop": "ssp_nat"}))
    else:
        wpp = read_wpp(config)
        proj_nat = wpp_ssp_projection_controls(config, scen)
        hist_nat = pop_linear_annual(
            wpp[wpp["year"] < 2020][["iso3", "year", "pop"]].rename(
                columns={"pop": "ssp_nat"}))
    hist_nat = hist_nat[hist_nat["year"].between(1981, 2019)]

    # Projection 2020-2100: fixed 2020 GHS shares times the SSP national total.
    ghs_base = ghs[ghs["year"] == wy][["hierid", "iso3", "pop"]].rename(
        columns={"pop": "ghs_ir"})
    ghs_nat = (ghs_base.groupby("iso3")["ghs_ir"].sum()
               .rename("ghs_nat").reset_index())
    ssp_countries = set(proj_nat["iso3"])
    proj = (ghs_base[ghs_base["iso3"].isin(ssp_countries)]
            .merge(ghs_nat, on="iso3")
            .merge(proj_nat, on="iso3"))
    proj = proj.assign(
        pop=proj["ghs_ir"] * (proj["ssp_nat"] * 1e6) / proj["ghs_nat"])[
        ["hierid", "iso3", "year", "pop"]]

    # Countries without SSP population: freeze at the GHS 2020 level.
    proj_years = np.arange(proj_nat["year"].min(), proj_nat["year"].max() + 1)
    no_ssp = set(ghs_base["iso3"]) - ssp_countries
    if no_ssp:
        frozen = (ghs_base[ghs_base["iso3"].isin(no_ssp)]
                  .merge(pd.DataFrame({"year": proj_years}), how="cross"))
        frozen = frozen.assign(pop=frozen["ghs_ir"])[
            ["hierid", "iso3", "year", "pop"]]
        proj = pd.concat([proj, frozen], ignore_index=True)

    # Historical 1981-2019: year-specific GHS shares (frozen at 1990 before).
    ghs_ys = ghs[(ghs["year"] >= 1990) & (ghs["year"] < wy)][
        ["hierid", "iso3", "year", "pop"]].rename(columns={"pop": "ghs_ir"})
    ghs_1990 = ghs[ghs["year"] == 1990][["hierid", "iso3", "pop"]].rename(
        columns={"pop": "ghs_ir"})
    ghs_pre = ghs_1990.merge(
        pd.DataFrame({"year": np.arange(1981, 1990)}), how="cross")
    ghs_hist = pd.concat(
        [ghs_pre[["hierid", "iso3", "year", "ghs_ir"]], ghs_ys],
        ignore_index=True)
    ghs_nat_hist = (ghs_hist.groupby(["iso3", "year"])["ghs_ir"].sum()
                    .rename("ghs_nat").reset_index())

    hist_countries = set(hist_nat["iso3"])
    hist = (ghs_hist[ghs_hist["iso3"].isin(hist_countries)]
            .merge(ghs_nat_hist, on=["iso3", "year"])
            .merge(hist_nat, on=["iso3", "year"]))
    share = np.where(hist["ghs_nat"] > 0, hist["ghs_ir"] / hist["ghs_nat"], 0)
    hist = hist.assign(pop=share * hist["ssp_nat"] * 1e6)[
        ["hierid", "iso3", "year", "pop"]]

    # Countries without SSP history: freeze at the year-specific GHS level.
    no_ssp_hist = set(ghs_hist["iso3"]) - hist_countries
    if no_ssp_hist:
        keep = ghs_hist[ghs_hist["iso3"].isin(no_ssp_hist)]
        hist = pd.concat(
            [hist, keep.assign(pop=keep["ghs_ir"])[
                ["hierid", "iso3", "year", "pop"]]],
            ignore_index=True)

    ir_pop = pd.concat([hist, proj], ignore_index=True)
    ir_pop = ir_pop.assign(scenario=scen)
    return ir_pop.sort_values(["hierid", "year"], ignore_index=True)[
        ["hierid", "iso3", "year", "scenario", "pop"]]
