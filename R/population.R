# IR-level population. National totals are distributed across IRs by GHS-POP
# shares: fixed 2020 shares for the projection (2020-2100), year-specific shares
# for history (1981-2019, frozen at 1990 before that). National control totals
# come from the SSP population model (pop_control IIASA, the reproduction) or,
# with pop_control UN_WPP, from UN WPP 2024 through the handoff year and from
# the SSP scenario trajectory, rebased to the WPP handoff level, afterwards.

# Linear interpolation of national population knots to annual, per iso3.
# Annual input passes through unchanged.
pop_linear_annual <- function(dt) {
  dt <- dt[!is.na(nat) & nat > 0]
  dt[, if (.N >= 2) {
    ys <- seq(min(year), max(year))
    list(year = ys, nat = stats::approx(year, nat, ys)$y)
  }, by = iso3]
}

# Handoff year for the UN_WPP control (deltas$pop_handoff_year, default 2023):
# the last year national totals follow UN WPP.
pop_handoff_year <- function(config) {
  h <- config$deltas$pop_handoff_year
  if (is.null(h)) h <- 2023
  h <- as.integer(h)
  if (is.na(h) || h < 2020 || h > 2099) {
    stop("pop_handoff_year must be between 2020 and 2099, got ", h)
  }
  h
}

# Projection-era national controls (millions, annual, 2020-2100) for
# pop_control UN_WPP: UN WPP through the handoff year H, then the scenario's
# SSP trajectory rebased to the WPP level at H -- nat(t) = WPP(H) * SSP(t) /
# SSP(H) -- so the national path is continuous at H and scenarios diverge
# from H+1. The multiplicative rebase is an open point for the team.
# Fallbacks: a country absent from the SSP scenario (or with a zero/missing
# anchor) stays on UN WPP in every year, which is the medium variant after
# the estimates end; a country absent from UN WPP gets no control here and
# keeps the frozen-GHS fallback in build_population.
wpp_ssp_projection_controls <- function(config, scen) {
  h <- pop_handoff_year(config)
  wpp <- read_wpp(config)
  ssp_ann <- pop_linear_annual(
    read_ssp(config)$pop[era == "projection" & scenario == scen,
                         .(iso3, year, nat = pop)])
  anchor <- merge(ssp_ann[year == h & nat > 0, .(iso3, ssp_h = nat)],
                  wpp[year == h & pop > 0, .(iso3, wpp_h = pop)],
                  by = "iso3")
  resc <- merge(ssp_ann[year > h], anchor, by = "iso3")
  resc <- resc[, .(iso3, year, nat = wpp_h * nat / ssp_h)]
  pre  <- wpp[year >= 2020 & year <= h & iso3 %in% anchor$iso3,
              .(iso3, year, nat = pop)]
  only <- wpp[year >= 2020 & !iso3 %in% anchor$iso3,
              .(iso3, year, nat = pop)]
  pop_linear_annual(rbind(pre, resc, only))
}

#' Build the IR-level population panel (1981-2100) in persons.
#'
#' @param config Parsed config.yml list.
#' @param scen SSP scenario for the projection national totals. Under UN_WPP
#'   it drives the years after the handoff; through the handoff the totals
#'   are the scenario-free UN WPP.
#' @return data.table(hierid, iso3, year, scenario, pop).
build_population <- function(config, scen = "SSP3") {
  # Delta #1 (pop_control): the national control totals, in millions.
  # "IIASA" scales to the SSP model totals in every year (the reproduction);
  # "UN_WPP" scales to UN WPP 2024 through the handoff year, then to the SSP
  # scenario trajectory rebased to the WPP handoff level. The GHS shares and
  # era logic are shared.
  pc <- config$deltas$pop_control
  if (!pc %in% c("IIASA", "UN_WPP")) {
    stop("build_population: unknown pop_control '", pc, "'")
  }

  ghs <- data.table::fread(file.path(config$paths$cache, "ir_pop_ghs.csv"))
  wy <- config$aggregation$pop_weight_year

  if (identical(pc, "IIASA")) {
    ssp_pop <- read_ssp(config)$pop
    proj_nat <- pop_linear_annual(ssp_pop[
      era == "projection" & scenario == scen, .(iso3, year, nat = pop)])
    hist_nat <- pop_linear_annual(
      ssp_pop[era == "historical", .(iso3, year, nat = pop)])
  } else {
    wpp <- read_wpp(config)
    proj_nat <- wpp_ssp_projection_controls(config, scen)
    hist_nat <- pop_linear_annual(wpp[year < 2020, .(iso3, year, nat = pop)])
  }
  hist_nat <- hist_nat[year >= 1981 & year <= 2019]

  # Projection 2020-2100: fixed 2020 GHS shares times the national total.
  ghs_base <- ghs[year == wy, .(hierid, iso3, ghs_ir = pop)]
  ghs_nat <- ghs[year == wy, .(ghs_nat = sum(pop)), by = iso3]
  nat_countries <- unique(proj_nat$iso3)
  proj <- merge(ghs_base[iso3 %in% nat_countries], ghs_nat, by = "iso3")
  proj <- merge(proj, proj_nat, by = "iso3", allow.cartesian = TRUE)
  proj[, pop := ghs_ir * (nat * 1e6) / ghs_nat]
  proj <- proj[, .(hierid, iso3, year, pop)]

  # Countries without a control total: freeze at the GHS 2020 level, all
  # years.
  proj_years <- range(proj_nat$year)
  no_nat <- setdiff(unique(ghs_base$iso3), nat_countries)
  if (length(no_nat) > 0) {
    frozen <- ghs_base[iso3 %in% no_nat][
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
  hist[, pop := share * nat * 1e6]
  hist <- hist[, .(hierid, iso3, year, pop)]

  # Countries without a historical control: freeze at the year-specific GHS
  # level.
  no_nat_hist <- setdiff(unique(ghs_hist$iso3), hist_countries)
  if (length(no_nat_hist) > 0) {
    hist <- rbind(hist,
                  ghs_hist[iso3 %in% no_nat_hist, .(hierid, iso3, year,
                                                    pop = ghs_ir)])
  }

  ir_pop <- rbind(hist, proj)
  ir_pop[, scenario := scen]
  ir_pop[order(hierid, year), .(hierid, iso3, year, scenario, pop)]
}
