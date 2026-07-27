# IR-level GDP per capita in 2005 PPP USD. Historical years calibrate the Kummu
# subnational shape to the PWT national level; projection years carry the 2023
# level forward with SSP growth. Values are in 2005 PPP throughout: PWT is
# deflated from 2021 and countries without PWT use Kummu deflated from 2017.

# BEA GDP deflator (2017 = 100): 2005 = 81.556, 2021 = 110.186.
PWT_TO_2005   <- 81.556 / 110.186
KUMMU_TO_2005 <- 81.556 / 100

# Log-linear interpolation of 5-year knots to annual, per iso3.
interp_annual <- function(dt) {
  dt <- dt[!is.na(gdppc) & gdppc > 0]
  dt[, if (.N >= 2) {
    ys <- seq(min(year), max(year))
    list(year = ys, gdppc = exp(stats::approx(year, log(gdppc), ys)$y))
  }, by = iso3]
}

# Growth relative to 2023 for the chosen GDP model, per iso3 x year (2024-2100).
# OECD is used directly. IIASA has no pre-2025 data, so its first two years are
# bridged with OECD growth and its own growth is chained from 2026. Countries
# with only IIASA use their 2025-2030 annualised rate for the first two years.
ssp_growth <- function(ssp_gdppc, gdp_model) {
  oecd <- interp_annual(ssp_gdppc[model == "OECD", .(iso3, year, gdppc)])
  oecd_g <- merge(oecd[year >= 2024],
                  oecd[year == 2023, .(iso3, base = gdppc)], by = "iso3")
  oecd_g <- oecd_g[, .(iso3, year, growth = gdppc / base)]

  iiasa <- interp_annual(ssp_gdppc[model == "IIASA", .(iso3, year, gdppc)])
  from25 <- merge(iiasa[year > 2025],
                  iiasa[year == 2025, .(iso3, b25 = gdppc)], by = "iso3")
  from25[, gf := gdppc / b25]
  g_o_25 <- oecd_g[year == 2025, .(iso3, g25 = growth)]

  with_oecd <- intersect(unique(iiasa$iso3), unique(oecd_g$iso3))
  bridge <- oecd_g[year %in% c(2024, 2025) & iso3 %in% with_oecd,
                   .(iso3, year, growth)]
  chained <- merge(from25[iso3 %in% with_oecd], g_o_25, by = "iso3")
  chained <- chained[, .(iso3, year, growth = g25 * gf)]
  iiasa_g <- rbind(bridge, chained)

  only <- setdiff(unique(iiasa$iso3), unique(oecd_g$iso3))
  if (length(only) > 0) {
    a <- iiasa[iso3 %in% only]
    ann <- merge(a[year == 2030, .(iso3, g30 = gdppc)],
                 a[year == 2025, .(iso3, g25 = gdppc)], by = "iso3")
    ann[, gann := (g30 / g25)^(1 / 5)]
    early <- ann[, .(year = c(2024L, 2025L), growth = c(gann, gann^2)),
                 by = iso3]
    g_only_25 <- early[year == 2025, .(iso3, g25 = growth)]
    late <- merge(from25[iso3 %in% only], g_only_25, by = "iso3")
    late <- late[, .(iso3, year, growth = g25 * gf)]
    iiasa_g <- rbind(iiasa_g, early, late)
  }

  # Cross-fill the missing model with the other (reference Step 3c): the IIASA
  # panel uses OECD growth for OECD-only countries, and the OECD panel uses
  # IIASA growth for IIASA-only countries.
  oecd_iso <- unique(oecd_g$iso3)
  iiasa_iso <- unique(iiasa_g$iso3)
  if (gdp_model == "IIASA") {
    rbind(iiasa_g, oecd_g[iso3 %in% setdiff(oecd_iso, iiasa_iso)])
  } else {
    rbind(oecd_g, iiasa_g[iso3 %in% setdiff(iiasa_iso, oecd_iso)])
  }
}

# Delta #2 (force_gdp_sum): rescale IR gdppc within each country-year so the
# population-weighted mean — and therefore the sum of IR GDP over the panel
# population — equals the SSP national gdppc (the level the book validates
# against, deflated 2017 -> 2005). Applied to the SSP-growth era (2024-2100)
# where the chosen model defines the national path; the PWT-anchored years
# stay untouched. Countries without an SSP national level keep their
# unconstrained values. Zero-population IRs scale with their country, which
# leaves the sum unchanged and preserves relative income shapes.
force_income_to_national <- function(income, config, scen, gdp_model,
                                     ssp_gdppc) {
  nat <- interp_annual(ssp_gdppc[model == gdp_model, .(iso3, year, gdppc)])
  nat <- nat[year >= 2024, .(iso3, year, nat_gdppc = gdppc * KUMMU_TO_2005)]
  pop <- build_population(config, scen)[, .(hierid, year, pop)]
  x <- merge(income, pop, by = c("hierid", "year"))
  wm <- x[!is.na(gdppc) & pop > 0,
          .(wmean = sum(gdppc * pop) / sum(pop)), by = .(iso3, year)]
  f <- merge(wm[wmean > 0], nat, by = c("iso3", "year"))
  f <- f[, .(iso3, year, factor = nat_gdppc / wmean)]
  income <- merge(income, f, by = c("iso3", "year"), all.x = TRUE)
  income[!is.na(factor), gdppc := gdppc * factor]
  income[, factor := NULL]
  income[]
}

# Replace Venezuela's 2012-2023 national level, where PWT's chained PPP breaks,
# with a log-linear path from PWT 2011 to the IIASA 2025 level, keeping the
# Kummu subnational shares. Values in 2005 PPP.
venezuela_income <- function(kummu_ir, adm0, pwt, ssp_gdppc) {
  p2011 <- pwt[iso3 == "VEN" & year == 2011, pwt]
  s2025 <- mean(
    ssp_gdppc[model == "IIASA" & iso3 == "VEN" & year == 2025, gdppc],
    na.rm = TRUE
  ) * KUMMU_TO_2005
  if (length(p2011) != 1 || is.na(p2011) || is.na(s2025)) return(NULL)
  yrs <- 2012:2023
  nat <- data.table::data.table(
    year = yrs,
    nat = p2011 * exp(log(s2025 / p2011) * (yrs - 2011) / (2025 - 2011))
  )
  k <- merge(kummu_ir[iso3 == "VEN" & year >= 2012 & year <= 2022],
             adm0[iso3 == "VEN", .(iso3, year, kummu_nat)],
             by = c("iso3", "year"))
  k <- merge(k, nat, by = "year")
  k <- k[!is.na(kummu_ir) & kummu_nat > 0,
         .(hierid, iso3, year, gdppc = (kummu_ir / kummu_nat) * nat)]
  g <- nat[year == 2023, nat] / nat[year == 2022, nat]
  k23 <- k[year == 2022][, `:=`(year = 2023L, gdppc = gdppc * g)]
  rbind(k, k23)
}

#' Build the IR-level GDP-per-capita panel in 2005 PPP USD.
#'
#' @param config Parsed config.yml list.
#' @param scen SSP scenario (projection growth).
#' @param gdp_model GDP model, "OECD" or "IIASA".
#' @return data.table(hierid, iso3, year, scenario, gdp_model, gdppc) 1990-2100.
build_income <- function(config, scen = "SSP3", gdp_model = "IIASA") {
  cache <- config$paths$cache
  kummu_ir <- data.table::fread(file.path(cache, "ir_gdppc_kummu.csv"))
  data.table::setnames(kummu_ir, "gdppc", "kummu_ir")
  pop_ghs <- data.table::fread(file.path(cache, "ir_pop_ghs.csv"))
  wy <- config$aggregation$pop_weight_year
  pop_base <- pop_ghs[year == wy, .(hierid, pop_base = pop)]

  km <- read_kummu(config)
  adm0 <- data.table::as.data.table(km$adm0)
  data.table::setnames(adm0, "gdppc", "kummu_nat")
  pwt <- read_pwt(config)
  pwt[, pwt := gdppc * PWT_TO_2005]
  ssp_gdppc <- read_ssp(config)$gdppc[scenario == scen]

  # Historical calibration, 1990-2022.
  h <- kummu_ir[year >= 1990 & year <= 2022, .(hierid, iso3, year, kummu_ir)]
  h <- merge(h, adm0[, .(iso3, year, kummu_nat)], by = c("iso3", "year"),
             all.x = TRUE)
  h <- merge(h, pwt[, .(iso3, year, pwt)], by = c("iso3", "year"), all.x = TRUE)
  h[, gdppc := NA_real_]
  h[!is.na(kummu_ir) & !is.na(kummu_nat) & kummu_nat > 0 & !is.na(pwt),
    gdppc := (kummu_ir / kummu_nat) * pwt]

  # Countries with no PWT at all: raw Kummu deflated 2017 -> 2005.
  has_iso <- unique(h[!is.na(gdppc), iso3])
  all_iso <- unique(h[!is.na(kummu_ir), iso3])
  no_pwt <- setdiff(all_iso, has_iso)
  h[iso3 %in% no_pwt & is.na(gdppc) & !is.na(kummu_ir),
    gdppc := kummu_ir * KUMMU_TO_2005]

  # IRs with no raster value: populated ones take a national fallback, the rest
  # stay NA (uninhabited).
  glob_pwt <- pwt[year >= 1990 & year <= 2022,
                  .(g_pwt = mean(pwt, na.rm = TRUE)), by = year]
  fb <- h[is.na(kummu_ir)]
  fb <- merge(fb, pop_base, by = "hierid", all.x = TRUE)
  fb <- merge(fb, glob_pwt, by = "year", all.x = TRUE)
  fb <- fb[!is.na(pop_base) & pop_base > 0.5]
  fb[, gval := data.table::fifelse(
    !is.na(pwt), pwt,
    data.table::fifelse(!is.na(kummu_nat), kummu_nat * KUMMU_TO_2005, g_pwt))]
  h[fb, gdppc := i.gval, on = c("hierid", "year")]

  hist <- h[, .(hierid, iso3, year, gdppc)]

  # Year 2023: roll 2022 forward by PWT growth, then SSP-implied, then a
  # global-average SSP growth.
  pw <- data.table::dcast(pwt[year %in% c(2022, 2023)], iso3 ~ year,
                          value.var = "pwt")
  data.table::setnames(pw, c("2022", "2023"), c("p22", "p23"))
  pw <- pw[!is.na(p22) & !is.na(p23) & p22 > 0, .(iso3, g_pwt = p23 / p22)]
  oecd_ann <- interp_annual(ssp_gdppc[model == "OECD", .(iso3, year, gdppc)])
  os <- data.table::dcast(oecd_ann[year %in% c(2022, 2023)], iso3 ~ year,
                          value.var = "gdppc")
  data.table::setnames(os, c("2022", "2023"), c("s22", "s23"))
  os <- os[!is.na(s22) & !is.na(s23) & s22 > 0, .(iso3, g_ssp = s23 / s22)]
  glob_g <- exp(mean(log(os$g_ssp)))
  y23 <- hist[year == 2022]
  y23 <- merge(y23, pw, by = "iso3", all.x = TRUE)
  y23 <- merge(y23, os, by = "iso3", all.x = TRUE)
  y23[, g := data.table::fcoalesce(g_pwt, g_ssp, glob_g)]
  y23 <- y23[, .(hierid, iso3, year = 2023L, gdppc = gdppc * g)]
  baseline <- rbind(hist, y23)

  # Venezuela: replace 2012-2023 with the interpolated national level.
  ven <- venezuela_income(kummu_ir, adm0, pwt, ssp_gdppc)
  if (!is.null(ven)) {
    baseline <- baseline[!(iso3 == "VEN" & year >= 2012)]
    baseline <- rbind(baseline, ven)
  }

  # Projections 2024-2100: 2023 level times SSP growth, with a global-average
  # growth fallback for countries the SSP does not cover.
  growth <- ssp_growth(ssp_gdppc, gdp_model)
  glob_growth <- growth[, .(growth = exp(mean(log(growth)))), by = year]
  base23 <- baseline[year == 2023, .(hierid, iso3, gdppc_2023 = gdppc)]
  covered <- unique(growth$iso3)
  need <- setdiff(unique(base23$iso3), covered)
  if (length(need) > 0) {
    growth <- rbind(growth,
                    data.table::CJ(iso3 = need)[, glob_growth[], by = iso3])
  }
  proj <- merge(base23, growth, by = "iso3", allow.cartesian = TRUE)
  proj <- proj[, .(hierid, iso3, year, gdppc = gdppc_2023 * growth)]

  income <- rbind(baseline, proj)

  # Delta #2 (force_gdp_sum): off in reproduction mode.
  if (isTRUE(config$deltas$force_gdp_sum)) {
    income <- force_income_to_national(income, config, scen, gdp_model,
                                       ssp_gdppc)
  }

  income[, `:=`(scenario = scen, gdp_model = gdp_model)]
  income[order(hierid, year), .(hierid, iso3, year, scenario, gdp_model, gdppc)]
}
