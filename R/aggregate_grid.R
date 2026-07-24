# One-time spatial aggregation of the Kummu rasters to IR polygons. Expensive
# (exactextractr over ~24,378 polygons x 33 bands), so the results are cached as
# CSVs under the cache path and downstream modules read the cache.

# Turn an exact_extract stack result (one column per band) into a long table
# keyed on hierid, iso3, year. Row order matches the polygon order in ids.
extract_to_long <- function(mat, ids, years, value_name) {
  dt <- data.table::as.data.table(mat)
  data.table::setnames(dt, as.character(years))
  dt <- cbind(ids, dt)
  long <- data.table::melt(dt, id.vars = c("hierid", "iso3"),
                           variable.name = "year", value.name = value_name)
  long[, year := as.integer(as.character(year))][]
}

#' Aggregate Kummu GDP and GHS-POP rasters to IR polygons and cache the result.
#'
#' @param kummu Output of read_kummu() (adm0, gdp_rast_path, pop_rast_path).
#' @param ir_shapes Output of read_ir_shapes() (sf polygons keyed on hierid).
#' @param config Parsed config.yml list.
#' @return invisibly, list(gdppc, pop, density, validation); each is also
#'   written as a CSV under config$paths$cache.
aggregate_kummu_to_ir <- function(kummu, ir_shapes, config) {
  gdp <- terra::rast(kummu$gdp_rast_path)
  pop <- terra::rast(kummu$pop_rast_path)
  stopifnot(terra::compareGeom(gdp, pop, stopOnError = FALSE))
  parse_years <- function(r) {
    as.integer(regmatches(names(r), regexpr("[0-9]{4}", names(r))))
  }
  gdp_years <- parse_years(gdp)
  pop_years <- parse_years(pop)

  ids <- data.table::data.table(
    hierid = ir_shapes$hierid,
    iso3   = sub("[.].*", "", ir_shapes$hierid)
  )

  # GDP per capita: population-weighted mean, weights = GHS-POP at the base
  # year. exact_extract weights each pixel by value * pop * coverage_fraction,
  # accounting for partial pixels. Where the weight sums to zero the mean
  # is NaN; fall back to the coverage-weighted area mean and flag those IRs.
  wy <- config$aggregation$pop_weight_year
  wi <- which(pop_years == wy)
  stopifnot(length(wi) == 1)
  weight <- terra::classify(pop[[wi]], cbind(NA, 0))
  message("Aggregating GDP per capita (population-weighted mean)...")
  wmean <- exactextractr::exact_extract(
    gdp, ir_shapes, "weighted_mean", weights = weight,
    stack_apply = TRUE, progress = FALSE
  )
  amean <- exactextractr::exact_extract(
    gdp, ir_shapes, "mean", stack_apply = TRUE, progress = FALSE
  )
  gdppc <- merge(
    extract_to_long(wmean, ids, gdp_years, "gdppc_w"),
    extract_to_long(amean, ids, gdp_years, "gdppc_a"),
    by = c("hierid", "iso3", "year")
  )
  gdppc[, zero_pop := is.nan(gdppc_w) | is.na(gdppc_w)]
  gdppc[, gdppc := data.table::fifelse(zero_pop, gdppc_a, gdppc_w)]
  gdppc[is.nan(gdppc), gdppc := NA_real_]
  gdppc <- gdppc[, .(hierid, iso3, year, gdppc, zero_pop)]
  message("  ", gdppc[(zero_pop), data.table::uniqueN(hierid)],
          " IRs used the area-mean fallback (zero population weight)")

  # Population: coverage-weighted zonal sum, all years.
  message("Aggregating population (zonal sum)...")
  psum <- exactextractr::exact_extract(
    pop, ir_shapes, "sum", stack_apply = TRUE, progress = FALSE
  )
  pop_ir <- extract_to_long(psum, ids, pop_years, "pop")

  # Population-weighted density: the density the average resident experiences.
  # For cells j in an IR this is sum(density_j * pop_j * cov) / sum(pop_j * cov)
  # with density_j = pop_j / area_j. That equals sum(pop_j^2 / area_j * cov)
  # over the population sum, so one zonal sum of pop^2/area gives every year.
  message("Aggregating population-weighted density...")
  area <- terra::cellSize(pop[[1]], unit = "km")
  num <- exactextractr::exact_extract(
    (pop * pop) / area, ir_shapes, "sum", stack_apply = TRUE, progress = FALSE
  )
  density <- merge(
    extract_to_long(num, ids, pop_years, "num"), pop_ir,
    by = c("hierid", "iso3", "year")
  )
  density[, pop_wtd_density := data.table::fifelse(pop > 0, num / pop, 0)]
  density <- density[, .(hierid, iso3, year, pop_wtd_density)]

  # Validation: national population-weighted mean of the IR GDP per capita,
  # compared with the Kummu ADM0 table.
  message("Validating national averages against Kummu ADM0...")
  natavg <- merge(gdppc[!is.na(gdppc)], pop_ir,
                  by = c("hierid", "iso3", "year"))
  natavg <- natavg[pop > 0, .(gdppc_natavg = stats::weighted.mean(gdppc, pop)),
                   by = .(iso3, year)]
  adm0 <- data.table::as.data.table(kummu$adm0)[, .(iso3, year,
                                                    gdppc_adm0 = gdppc)]
  validation <- merge(natavg, adm0, by = c("iso3", "year"))
  validation[, `:=`(ratio = gdppc_natavg / gdppc_adm0,
                    pct_diff = (gdppc_natavg - gdppc_adm0) / gdppc_adm0 * 100)]
  vy <- validation[year == wy]
  thr <- config$aggregation$validation_pct
  message("  Year ", wy, ": median ratio ",
          round(stats::median(vy$ratio, na.rm = TRUE), 4), ", ",
          nrow(vy[abs(pct_diff) > thr]), " countries over ", thr, "%")

  # Cache
  cache <- config$paths$cache
  if (!dir.exists(cache)) dir.create(cache, recursive = TRUE)
  data.table::fwrite(gdppc, file.path(cache, "ir_gdppc_kummu.csv"))
  data.table::fwrite(pop_ir, file.path(cache, "ir_pop_ghs.csv"))
  data.table::fwrite(density, file.path(cache, "ir_pop_wtd_density.csv"))
  data.table::fwrite(validation, file.path(cache, "ir_kummu_validation.csv"))
  message("Cached 4 CSVs under ", cache)

  invisible(list(gdppc = gdppc, pop = pop_ir, density = density,
                 validation = validation))
}
