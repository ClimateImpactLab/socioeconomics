# Final assembly and cleaning: join income, population, and cohorts into the wide
# panel, smooth income, and derive area, density, and gdp.

#' Assemble and post-process the final IR panel.
#'
#' @param income Output of the income chain (post special cases).
#' @param population Output of build_population().
#' @param cohorts Output of build_cohorts().
#' @param ir_shapes Output of read_ir_shapes() (for geodesic area).
#' @param config Parsed config.yml list.
#' @return data.table, one row per hierid x year x scenario x gdp_model (see docs/data_dictionary.yml).
postprocess_panel <- function(income, population, cohorts, ir_shapes, config) {
  # Impute pre-raster income as each IR's historical mean, then smooth from the
  # transition year with a 13-year backward half-Bartlett kernel; gdp = gdppc * pop.
  stop("not implemented")
}
