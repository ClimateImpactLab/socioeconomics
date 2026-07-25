# IR-level population. National totals are distributed across IRs by GHS-POP
# shares: fixed 2020 shares for the projection (2020-2100), year-specific shares
# for history (1981-2019, frozen at 1990 before that). National totals come from
# the SSP population model.

# Linear interpolation of national population knots to annual, per iso3.
pop_linear_annual <- function(dt) {
  dt <- dt[!is.na(ssp_nat) & ssp_nat > 0]
  dt[, if (.N >= 2) {
    ys <- seq(min(year), max(year))
    list(year = ys, ssp_nat = stats::approx(year, ssp_nat, ys)$y)
  }, by = iso3]
}

#' Build the IR-level population panel (1981-2100) in persons.
#'
#' @param config Parsed config.yml list.
#' @param scen SSP scenario for the projection national totals.
#' @return data.table(hierid, iso3, year, scenario, pop).
build_population <- function(config, scen = "SSP3") {
  # Delta #1 (pop_control): "IIASA" scales to SSP national totals (below);
  # "UN_WPP" would scale to UN WPP totals. Reproduction uses IIASA.
  if (!identical(config$deltas$pop_control, "IIASA")) {
    stop("build_population: only pop_control IIASA is implemented")
  }

  ghs <- data.table::fread(file.path(config$paths$cache, "ir_pop_ghs.csv"))
  wy <- config$aggregation$pop_weight_year
  ssp_pop <- read_ssp(config)$pop

  # National SSP population (millions), both eras.
  proj_nat <- pop_linear_annual(ssp_pop[
    era == "projection" & scenario == scen, .(iso3, year, ssp_nat = pop)])
  hist_nat <- pop_linear_annual(
    ssp_pop[era == "historical", .(iso3, year, ssp_nat = pop)])
  hist_nat <- hist_nat[year >= 1981 & year <= 2019]

  # Projection 2020-2100: fixed 2020 GHS shares times the SSP national total.
  ghs_base <- ghs[year == wy, .(hierid, iso3, ghs_ir = pop)]
  ghs_nat <- ghs[year == wy, .(ghs_nat = sum(pop)), by = iso3]
  ssp_countries <- unique(proj_nat$iso3)
  proj <- merge(ghs_base[iso3 %in% ssp_countries], ghs_nat, by = "iso3")
  proj <- merge(proj, proj_nat, by = "iso3", allow.cartesian = TRUE)
  proj[, pop := ghs_ir * (ssp_nat * 1e6) / ghs_nat]
  proj <- proj[, .(hierid, iso3, year, pop)]

  # Countries without SSP population: freeze at the GHS 2020 level, all years.
  proj_years <- range(proj_nat$year)
  no_ssp <- setdiff(unique(ghs_base$iso3), ssp_countries)
  if (length(no_ssp) > 0) {
    frozen <- ghs_base[iso3 %in% no_ssp][
      , data.table::CJ(year = proj_years[1]:proj_years[2]),
      by = .(hierid, iso3)]
    frozen <- merge(frozen, ghs_base, by = c("hierid", "iso3"))
    proj <- rbind(proj, frozen[, .(hierid, iso3, year, pop = ghs_ir)])
  }

  # Historical 1981-2019: year-specific GHS shares (frozen at 1990 before 1990).
  ghs_ys <- ghs[year >= 1990 & year < wy, .(hierid, iso3, year, ghs_ir = pop)]
  ghs_1990 <- ghs[year == 1990, .(hierid, iso3, ghs_ir = pop)]
  ghs_pre <- ghs_1990[, data.table::CJ(year = 1981:1989), by = .(hierid, iso3)]
  ghs_pre <- merge(ghs_pre, ghs_1990, by = c("hierid", "iso3"))
  ghs_hist <- rbind(ghs_pre[, .(hierid, iso3, year, ghs_ir)], ghs_ys)
  ghs_nat_hist <- ghs_hist[, .(ghs_nat = sum(ghs_ir)), by = .(iso3, year)]

  hist_countries <- unique(hist_nat$iso3)
  hist <- merge(ghs_hist[iso3 %in% hist_countries], ghs_nat_hist,
                by = c("iso3", "year"))
  hist <- merge(hist, hist_nat, by = c("iso3", "year"))
  hist[, share := data.table::fifelse(ghs_nat > 0, ghs_ir / ghs_nat, 0)]
  hist[, pop := share * ssp_nat * 1e6]
  hist <- hist[, .(hierid, iso3, year, pop)]

  # Countries without SSP history: freeze at the year-specific GHS level.
  no_ssp_hist <- setdiff(unique(ghs_hist$iso3), hist_countries)
  if (length(no_ssp_hist) > 0) {
    hist <- rbind(hist,
                  ghs_hist[iso3 %in% no_ssp_hist, .(hierid, iso3, year,
                                                    pop = ghs_ir)])
  }

  ir_pop <- rbind(hist, proj)
  ir_pop[, scenario := scen]
  ir_pop[order(hierid, year), .(hierid, iso3, year, scenario, pop)]
}
