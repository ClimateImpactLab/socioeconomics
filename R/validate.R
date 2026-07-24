# Diagnostic comparisons. These report only; they do not gate the writers.

# Deflator from 2021 to 2005 PPP USD (BEA GDP implicit price deflator), so PWT
# levels can be compared with the reference panel, which is in 2005 PPP USD.
PWT_TO_2005 <- 0.74017

#' Aggregate the reference IR panel to national income, population, and cohorts.
#'
#' @param config Parsed config.yml list.
#' @return data.table(iso3, year, pop_nat, gdppc_nat, share_0_4, share_5_64,
#'   share_65plus). gdppc_nat is the population-weighted mean of the raw IR
#'   income (gdppc_raw0), not the smoothed gdppc, so it holds the actual income
#'   level; the weighted mean covers only IRs with a positive raw value.
reference_national <- function(config) {
  ref <- data.table::fread(
    file.path(config$paths$reference, config$inputs$reference),
    select = c("iso3", "year", "gdppc_raw0", "pop",
               "pop0to4", "pop5to64", "pop65plus")
  )
  ref <- ref[pop > 0]
  ref[, .(
    pop_nat      = sum(pop),
    gdppc_nat    = sum(gdppc_raw0 * pop) / sum(pop * (gdppc_raw0 > 0)),
    share_0_4    = sum(pop0to4) / sum(pop),
    share_5_64   = sum(pop5to64) / sum(pop),
    share_65plus = sum(pop65plus) / sum(pop)
  ), by = .(iso3, year)][order(iso3, year)]
}

# Year-over-year growth of a value within each group, ordered by year.
yoy_growth <- function(x) c(NA_real_, x[-1] / x[-length(x)])

#' Compare national income level and growth against read_pwt.
#'
#' @param config Parsed config.yml list.
#' @return data.table(iso3, year, gdppc_ref, gdppc_pwt, ratio, pct_diff,
#'   growth_ref, growth_pwt, flag). PWT is deflated 2021 -> 2005 PPP USD.
compare_income_pwt <- function(config) {
  ref <- reference_national(config)[, .(iso3, year, gdppc_ref = gdppc_nat)]
  pwt <- read_pwt(config)[, .(iso3, year, gdppc_pwt = gdppc * PWT_TO_2005)]
  m <- merge(ref, pwt, by = c("iso3", "year"), all.x = TRUE)
  data.table::setorder(m, iso3, year)
  m[, `:=`(
    growth_ref = yoy_growth(gdppc_ref),
    growth_pwt = yoy_growth(gdppc_pwt)
  ), by = iso3]
  pwt_iso <- unique(pwt$iso3)
  m[, `:=`(
    ratio    = gdppc_ref / gdppc_pwt,
    pct_diff = (gdppc_ref - gdppc_pwt) / gdppc_pwt * 100,
    flag = data.table::fifelse(
      iso3 == "VEN", "venezuela",
      data.table::fifelse(!iso3 %in% pwt_iso, "no_pwt", "")
    )
  )]
  m[order(iso3, year)]
}

#' Compare national age-cohort shares against read_ssp.
#'
#' @param config Parsed config.yml list.
#' @param scen SSP scenario to compare projection years against.
#' @return data.table(iso3, year, share_*_ref, share_*_ssp, and their diffs).
compare_cohorts_ssp <- function(config, scen = "SSP3") {
  ref <- reference_national(config)[
    , .(iso3, year, share_0_4, share_5_64, share_65plus)]
  coh <- read_ssp(config)$cohorts
  tot <- coh$age0to4 + coh$age5to64 + coh$age65plus
  coh <- coh[tot > 0]
  # Historical era covers up to 2025 and projection from 2020; use historical
  # before 2020 and the scenario projection from 2020 so each year appears once.
  ssp <- coh[(era == "historical" & year < 2020) |
               (era == "projection" & scenario == scen & year >= 2020)]
  ssp <- ssp[, .(
    s0_4    = sum(age0to4) / sum(age0to4 + age5to64 + age65plus),
    s5_64   = sum(age5to64) / sum(age0to4 + age5to64 + age65plus),
    s65     = sum(age65plus) / sum(age0to4 + age5to64 + age65plus)
  ), by = .(iso3, year)]
  m <- merge(ref, ssp, by = c("iso3", "year"))
  m[, `:=`(
    diff_0_4    = share_0_4 - s0_4,
    diff_5_64   = share_5_64 - s5_64,
    diff_65plus = share_65plus - s65
  )]
  m[order(iso3, year)]
}

#' Compare national population totals between read_wpp and read_ssp (IIASA-WiC).
#'
#' @param config Parsed config.yml list.
#' @param scen SSP scenario whose projection population is used.
#' @return data.table(iso3, year, pop_wpp, pop_ssp, ratio, pct_diff).
compare_pop_sources <- function(config, scen = "SSP3") {
  wpp <- read_wpp(config)[, .(iso3, year, pop_wpp = pop)]
  ssp <- read_ssp(config)$pop
  # Historical era covers up to 2025 and projection from 2020; use historical
  # before 2020 and the scenario projection from 2020 so each year appears once.
  ssp <- ssp[(era == "historical" & year < 2020) |
               (era == "projection" & scenario == scen & year >= 2020),
             .(iso3, year, pop_ssp = pop)]
  m <- merge(wpp, ssp, by = c("iso3", "year"))
  m[, `:=`(ratio = pop_wpp / pop_ssp,
           pct_diff = (pop_wpp - pop_ssp) / pop_ssp * 100)]
  m[order(iso3, year)]
}

#' Compare the finished panel against the benchmark.
#'
#' @param panel Output of postprocess_panel().
#' @param benchmark Output of read_benchmark().
#' @param config Parsed config.yml list.
#' @return list of comparison diagnostics.
validate_against_benchmark <- function(panel, benchmark, config) {
  stop("not implemented")
}
