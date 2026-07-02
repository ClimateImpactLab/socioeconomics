# Hard assertions on the final panel. Runs before the writers so tar_make()
# halts on any violation.

#' Assert the panel's invariants before writing.
#'
#' @param panel Output of postprocess_panel().
#' @param config Parsed config.yml list.
#' @return checks report, invisibly, on success.
check_panel <- function(panel, config) {
  # Non-negativity; complete hierid x year x scenario x gdp_model grid; cohorts
  # sum to pop; and the delta invariants: force_gdp_sum => sum_IR(gdp) matches
  # national GDP within tolerance, pop_control UN_WPP => totals match UN WPP.
  stop("not implemented")
}
