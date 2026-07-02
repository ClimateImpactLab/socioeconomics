# IR-level population: national control totals distributed across IRs by GHS-POP
# base-year shares.

#' Build the IR-level population panel (1981-2100).
#'
#' @param ir_grid Output of aggregate_kummu_to_ir() (GHS-POP per IR).
#' @param wpp Output of read_wpp() (UN WPP control totals).
#' @param ssp Output of read_ssp() (IIASA-WiC control totals, book mode).
#' @param config Parsed config.yml list.
#' @return data.table(hierid, iso3, year, scenario, pop).
build_population <- function(ir_grid, wpp, ssp, config) {
  # Delta #1 (pop_control): "UN_WPP" uses UN WPP 2024 national totals (CIL 2.0),
  # "IIASA" uses IIASA-WiC SSP totals (reproduce book), via
  # pop_ir_t = pop_ghs_ir * (control_t / pop_ghs_national). Countries absent from
  # the chosen control are frozen at GHS-POP level.
  stop("not implemented")
}
