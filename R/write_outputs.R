# Serialize the combination panels into the canonical Zarr store. The store
# mirrors the benchmark layout (integration-econ-bc39.zarr) so it is a
# drop-in replacement: dims (ssp, region, model, year), float32 variables,
# model labels "IIASA GDP" / "OECD Env-Growth", plus the additional panel
# variables (raw income, cohorts, densities, area) new consumers can use.

#' Assemble the per-combination panel CSVs into one Zarr store.
#'
#' Zarr has no dependable R writer, so the serialization runs in Python
#' (data/panels_to_zarr.py), which needs pandas, numpy, xarray, and zarr;
#' the interpreter is resolved by resolve_python (io.R), overridable with
#' the PYTHON environment variable.
#'
#' @param config Parsed config.yml list.
#' @param panel_files Character vector of ir_combined_<scen>_<model>.csv
#'   paths, one per combination.
#' @return The store path, invisibly.
write_zarr <- function(config, panel_files) {
  out <- file.path(config$paths$output, "ir_combined.zarr")
  py <- resolve_python()
  status <- system2(py, c(
    shQuote(file.path("data", "panels_to_zarr.py")),
    shQuote(out),
    vapply(panel_files, shQuote, character(1))
  ))
  if (status != 0) {
    stop("panels_to_zarr.py failed with status ", status)
  }
  invisible(out)
}
