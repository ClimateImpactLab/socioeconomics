"""IR-level age-cohort populations (0-4 / 5-64 / 65+), mirroring R/cohorts.R.

National age shares are held constant between 5-year knots (a step function,
unlike population's linear interpolation) and applied uniformly to every IR in
a country, then multiplied by the IR population so the cohorts sum to the IR
total. Historical shares (1980-2015 knots) come from the SSP Historical
Reference, projection shares (2020-2100) from the scenario.
"""

import numpy as np
import pandas as pd

from .io import read_ssp
from .population import build_population

SHARE_COLS = ["share_0_4", "share_5_64", "share_65plus"]


def build_cohorts(config, scen="SSP3"):
    """Build IR-level age-cohort populations (1981-2100) in persons.

    :param config: parsed config dict.
    :param scen: SSP scenario for the projection shares.
    :return: DataFrame(hierid, iso3, year, scenario, pop0to4, pop5to64,
        pop65plus).
    """
    ssp = read_ssp(config)

    # National shares at the knots: age bin over the total population.
    # Historical is scenario-free (1980-2015); projection is
    # scenario-specific (2020-2100).
    tot = ssp["pop"].rename(columns={"pop": "pop_total"})
    s = ssp["cohorts"].merge(tot, on=["era", "scenario", "iso3", "year"])
    s = s[s["pop_total"] > 0]
    s = s.assign(share_0_4=s["age0to4"] / s["pop_total"],
                 share_5_64=s["age5to64"] / s["pop_total"],
                 share_65plus=s["age65plus"] / s["pop_total"])
    hist_sh = s[(s["era"] == "historical")
                & s["year"].between(1980, 2015)][["iso3", "year"] + SHARE_COLS]
    proj_sh = s[(s["era"] == "projection") & (s["scenario"] == scen)
                & (s["year"] >= 2020)][["iso3", "year"] + SHARE_COLS]
    shares = pd.concat([hist_sh, proj_sh], ignore_index=True)

    countries_with_age = set(shares["iso3"])
    knots = np.sort(shares["year"].unique())

    # Global-average fallback: unweighted mean of national shares per year.
    fb = shares.groupby("year")[SHARE_COLS].mean().reset_index()

    # Step function: each annual year takes the most recent knot at or
    # before it.
    years = np.arange(1981, 2101)
    kmap = pd.DataFrame({
        "year": years,
        "knot": knots[np.searchsorted(knots, years, side="right") - 1],
    })
    csh = kmap.merge(shares.rename(columns={"year": "knot"}), on="knot")
    fbsh = kmap.merge(fb.rename(columns={"year": "knot"}), on="knot")

    # Apply to IRs via their population, using country shares where available
    # and the global-average fallback otherwise.
    ir_pop = build_population(config, scen)
    in_age = ir_pop["iso3"].isin(countries_with_age)
    with_sh = ir_pop[in_age].merge(
        csh[["iso3", "year"] + SHARE_COLS], on=["iso3", "year"])
    no_sh = ir_pop[~in_age].merge(fbsh[["year"] + SHARE_COLS], on="year")
    ir = pd.concat([with_sh, no_sh], ignore_index=True)

    ir = ir.assign(pop0to4=ir["pop"] * ir["share_0_4"],
                   pop5to64=ir["pop"] * ir["share_5_64"],
                   pop65plus=ir["pop"] * ir["share_65plus"])
    return ir.sort_values(["hierid", "year"], ignore_index=True)[
        ["hierid", "iso3", "year", "scenario",
         "pop0to4", "pop5to64", "pop65plus"]]
