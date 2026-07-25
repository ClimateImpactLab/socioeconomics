# Assemble the final IR panel in the shape of ir_combined and apply the
# reference postprocessing: impute early income, Bartlett-smooth from 2016,
# derive gdp and densities, and fill missing values with zero.

# Backward half-Bartlett kernel (window 13). For year i the weights are
# 13, 12, ... over the current and past values x[(i - max_lag):i]; at the start
# the window truncates and renormalises over the available lags.
bartlett_smooth <- function(x, window = 13L) {
  n <- length(x)
  out <- numeric(n)
  for (i in seq_len(n)) {
    max_lag <- min(i - 1L, window - 1L)
    lags <- 0:max_lag
    weights <- window - lags
    vals <- x[(i - max_lag):i]
    valid <- !is.na(vals)
    if (any(valid)) {
      out[i] <- sum(vals[valid] * weights[valid]) / sum(weights[valid])
    } else {
      out[i] <- NA_real_
    }
  }
  out
}

# Geodesic IR area in km2 from the shapefile.
compute_ir_area <- function(config) {
  shp <- sf::st_read(config$paths$ir_shapes, quiet = TRUE)
  if (is.na(sf::st_crs(shp))) sf::st_crs(shp) <- 4326
  shp <- sf::st_make_valid(shp)
  data.table::data.table(hierid = shp$hierid,
                         area_km2 = as.numeric(sf::st_area(shp)) / 1e6)
}

#' Assemble and post-process the final IR panel.
#'
#' @param config Parsed config.yml list.
#' @param scen SSP scenario.
#' @param gdp_model GDP model, "OECD" or "IIASA".
#' @return data.table with the ir_combined data columns (hierid, iso3, year,
#'   gdppc, gdppc_raw, gdppc_raw0, gdp, pop, area_km2, pop_density,
#'   pop_wtd_density, pop0to4, pop5to64, pop65plus).
postprocess_panel <- function(config, scen = "SSP3", gdp_model = "IIASA") {
  # Raw income (1990-2100), extended with empty 1981-1989.
  raw <- build_income(config, scen, gdp_model)[
    , .(hierid, iso3, year, gdppc_raw = gdppc)]
  ids <- unique(raw[, .(hierid, iso3)])
  pre <- ids[, data.table::CJ(year = 1981:1989), by = .(hierid, iso3)]
  pre[, gdppc_raw := NA_real_]
  raw <- rbind(pre[, .(hierid, iso3, year, gdppc_raw)], raw)

  # Smoothed income: 1981-2015 imputed as each IR's 1990-2015 mean, 2016+ the
  # Bartlett kernel over that series; missing set to 0.
  imp <- raw[year >= 1990 & year <= 2015,
             .(m = mean(gdppc_raw, na.rm = TRUE)), by = hierid]
  ser <- merge(raw, imp, by = "hierid", all.x = TRUE)
  ser[, gser := data.table::fifelse(year <= 2015, m, gdppc_raw)]
  data.table::setorder(ser, hierid, year)
  ser[, gsm := bartlett_smooth(gser), by = hierid]
  ser[, gdppc := data.table::fifelse(year >= 2016, gsm, gser)]
  ser[is.na(gdppc), gdppc := 0]
  ser[, gdppc_raw0 := data.table::fifelse(
    year >= 1990,
    data.table::fifelse(is.na(gdppc_raw), 0, gdppc_raw), gdppc_raw)]

  pop <- build_population(config, scen)[, .(hierid, iso3, year, pop)]
  coh <- build_cohorts(config, scen)[
    , .(hierid, year, pop0to4, pop5to64, pop65plus)]
  area <- compute_ir_area(config)
  pwd <- data.table::fread(
    file.path(config$paths$cache, "ir_pop_wtd_density.csv"))[
    year == config$aggregation$pop_weight_year, .(hierid, pop_wtd_density)]

  panel <- merge(ser[, .(hierid, iso3, year, gdppc, gdppc_raw, gdppc_raw0)],
                 pop, by = c("hierid", "iso3", "year"), all.x = TRUE)
  panel <- merge(panel, coh, by = c("hierid", "year"), all.x = TRUE)
  panel <- merge(panel, area, by = "hierid", all.x = TRUE)
  panel <- merge(panel, pwd, by = "hierid", all.x = TRUE)

  for (col in c("pop", "pop_wtd_density", "pop0to4", "pop5to64", "pop65plus")) {
    panel[is.na(get(col)), (col) := 0]
  }
  panel[, gdp := gdppc * pop]
  panel[, pop_density := data.table::fifelse(area_km2 > 0, pop / area_km2, 0)]

  panel[order(hierid, year),
        .(hierid, iso3, year, gdppc, gdppc_raw, gdppc_raw0, gdp, pop,
          area_km2, pop_density, pop_wtd_density, pop0to4, pop5to64, pop65plus)]
}
