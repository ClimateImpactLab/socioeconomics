# IR-level GDP per capita: Kummu subnational shape times PWT national level for
# history, rolled forward with SSP growth. Special cases live in special_cases.R.

#' Build the IR-level GDP-per-capita panel (historical and projected).
#'
#' @param ir_grid Output of aggregate_kummu_to_ir().
#' @param pwt Output of read_pwt().
#' @param ssp Output of read_ssp().
#' @param config Parsed config.yml list.
#' @return data.table(hierid, iso3, year, scenario, gdp_model, gdppc).
build_income <- function(ir_grid, pwt, ssp, config) {
  # Delta #2 (force_gdp_sum): when true, rescale each country's IR gdppc so
  # sum_IR(gdppc * pop) matches national GDP within tolerances$gdp_sum_pct; when
  # false, reproduce the book, which only matches the national pop-weighted mean.
  # The rescale needs population, so the toggle is threaded to where pop is joined.
  stop("not implemented")
}
