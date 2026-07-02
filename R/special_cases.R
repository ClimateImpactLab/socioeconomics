# Targeted corrections applied to the income chain as explicit pipeline steps.

#' Correct Venezuela's post-2011 income for broken PWT PPP.
#'
#' @param income Income panel from build_income().
#' @param pwt Output of read_pwt().
#' @param ssp Output of read_ssp().
#' @param config Parsed config.yml list.
#' @return income panel with VEN corrected.
venezuela_fix <- function(income, pwt, ssp, config) {
  # PWT chained PPP breaks after the 2011 ICP survey during hyperinflation;
  # interpolate the national level between trusted anchors and keep Kummu shares.
  stop("not implemented")
}

#' Fill SSP growth for countries missing a model or all SSP GDP.
#'
#' @param income Income panel from venezuela_fix().
#' @param ssp Output of read_ssp().
#' @param config Parsed config.yml list.
#' @return income panel with coverage gaps filled.
coverage_fallback <- function(income, ssp, config) {
  # Duplicate the available model where only one exists; use global-average
  # (geometric-mean) growth where a country has no SSP GDP at all.
  stop("not implemented")
}

#' Set gdppc to NA for uninhabited IRs.
#'
#' @param income Income panel from coverage_fallback().
#' @param ir_grid Output of aggregate_kummu_to_ir() (for base-year population).
#' @return income panel with uninhabited IRs set to NA gdppc.
uninhabited_zero <- function(income, ir_grid) {
  # IRs with no raster cell and near-zero base-year population carry no weight
  # downstream (Carleton-consistent); populated no-cell IRs are handled upstream.
  stop("not implemented")
}
