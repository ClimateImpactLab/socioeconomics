# IR-level age cohorts: national SSP age shares applied uniformly within each
# country, times the IR population.

#' Build IR-level age-cohort populations (0-4, 5-64, 65+).
#'
#' @param population Output of build_population().
#' @param ssp Output of read_ssp().
#' @param config Parsed config.yml list.
#' @return data.table(hierid, iso3, year, scenario, pop0to4, pop5to64,
#'   pop65plus).
build_cohorts <- function(population, ssp, config) {
  # Shares binned to 0-4 / 5-64 / 65+, held as a step function between 5-year
  # knots; countries without SSP age data fall back to the cross-country mean.
  stop("not implemented")
}
