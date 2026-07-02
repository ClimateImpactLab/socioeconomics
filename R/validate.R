# Diagnostic comparison of the panel against the Carleton benchmark. Reports
# only; it does not gate the writers.

#' Compare the panel against the Carleton benchmark.
#'
#' @param panel Output of postprocess_panel().
#' @param benchmark Output of read_benchmark().
#' @param config Parsed config.yml list.
#' @return list of comparison diagnostics.
validate_against_benchmark <- function(panel, benchmark, config) {
  # Benchmark is a Zarr store, not CIL_Socioecon.nc; the reader lives in io.R.
  stop("not implemented")
}
