# IR-level age-cohort populations (0-4 / 5-64 / 65+). National age shares are
# held constant between 5-year knots (a step function) and applied uniformly to
# every IR in a country, then multiplied by the IR population so the cohorts sum
# to the IR total. Historical shares (1980-2015 knots) come from the SSP
# Historical Reference, projection shares (2020-2100) from the scenario.

#' Build IR-level age-cohort populations (1981-2100) in persons.
#'
#' @param config Parsed config.yml list.
#' @param scen SSP scenario for the projection shares.
#' @return data.table(hierid, iso3, year, scenario, pop0to4, pop5to64,
#'   pop65plus).
build_cohorts <- function(config, scen = "SSP3") {
  ssp <- read_ssp(config)

  # National shares at the knots: age bin over the total population. Historical
  # is scenario-free (1980-2015); projection is scenario-specific (2020-2100).
  tot <- ssp$pop[, .(era, scenario, iso3, year, pop_total = pop)]
  s <- merge(ssp$cohorts, tot, by = c("era", "scenario", "iso3", "year"))
  s <- s[pop_total > 0]
  s[, `:=`(share_0_4 = age0to4 / pop_total,
           share_5_64 = age5to64 / pop_total,
           share_65plus = age65plus / pop_total)]
  hist_sh <- s[era == "historical" & year >= 1980 & year <= 2015,
               .(iso3, year, share_0_4, share_5_64, share_65plus)]
  proj_sh <- s[era == "projection" & scenario == scen & year >= 2020,
               .(iso3, year, share_0_4, share_5_64, share_65plus)]
  shares <- rbind(hist_sh, proj_sh)

  countries_with_age <- unique(shares$iso3)
  knots <- sort(unique(shares$year))

  # Global-average fallback: unweighted mean of national shares per year.
  fb <- shares[, .(share_0_4 = mean(share_0_4),
                   share_5_64 = mean(share_5_64),
                   share_65plus = mean(share_65plus)), by = year]

  # Step function: each annual year takes the most recent knot at or before it.
  kmap <- data.table::data.table(year = 1981:2100)
  kmap[, knot := knots[findInterval(year, knots)]]

  sh_k <- data.table::copy(shares)
  data.table::setnames(sh_k, "year", "knot")
  csh <- merge(kmap, sh_k, by = "knot", allow.cartesian = TRUE)
  fb_k <- data.table::copy(fb)
  data.table::setnames(fb_k, "year", "knot")
  fbsh <- merge(kmap, fb_k, by = "knot")

  # Apply to IRs via their population, using country shares where available and
  # the global-average fallback otherwise.
  ir_pop <- build_population(config, scen)
  with_sh <- merge(ir_pop[iso3 %in% countries_with_age],
                   csh[, .(iso3, year, share_0_4, share_5_64, share_65plus)],
                   by = c("iso3", "year"))
  no_sh <- merge(ir_pop[!iso3 %in% countries_with_age],
                 fbsh[, .(year, share_0_4, share_5_64, share_65plus)],
                 by = "year")
  ir <- rbind(with_sh, no_sh)

  ir[, `:=`(pop0to4 = pop * share_0_4,
            pop5to64 = pop * share_5_64,
            pop65plus = pop * share_65plus)]
  ir[order(hierid, year),
     .(hierid, iso3, year, scenario, pop0to4, pop5to64, pop65plus)]
}
