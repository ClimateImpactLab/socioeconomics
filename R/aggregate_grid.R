# One-time spatial aggregation of the Kummu rasters to IR polygons. Expensive
# (exactextractr over ~24,378 polygons x many bands), so targets caches it and
# only recomputes when the rasters or boundaries change.

#' Aggregate Kummu GDP and GHS-POP rasters to IR polygons.
#'
#' @param kummu Output of read_kummu().
#' @param ir_shapes Output of read_ir_shapes().
#' @param config Parsed config.yml list.
#' @return data.table(hierid, iso3, year, gdppc_kummu_ir, pop_ghs_ir,
#'   pop_wtd_density, zero_pop).
aggregate_kummu_to_ir <- function(kummu, ir_shapes, config) {
  # GDP pc is a population-weighted mean (area-mean fallback where population is
  # zero); population is a zonal sum; both per IR per year.
  stop("not implemented")
}
