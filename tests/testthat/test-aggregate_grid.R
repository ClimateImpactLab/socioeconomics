# Tests for R/aggregate_grid.R. Runs the aggregation on a couple of synthetic
# polygons over the real Kummu rasters (cropped to a small window for speed), so
# it exercises exact_extract and every output without the full IR shapefile.
# Skips if the rasters or exactextractr are absent.

test_that("aggregate_kummu_to_ir produces cached per-IR tables", {
  skip_if_not(requireNamespace("terra", quietly = TRUE))
  skip_if_not(requireNamespace("sf", quietly = TRUE))
  skip_if_not(requireNamespace("exactextractr", quietly = TRUE))
  cfg <- io_setup()
  root <- find_repo_root()
  sys.source(file.path(root, "R", "aggregate_grid.R"), envir = environment())
  gdp_path <- file.path(cfg$paths$source, cfg$inputs$kummu_gdp_rast)
  pop_path <- file.path(cfg$paths$source, cfg$inputs$kummu_pop_rast)
  skip_if_not(file.exists(gdp_path) && file.exists(pop_path),
              "Kummu rasters not present")

  km <- read_kummu(cfg)
  # Crop to a window covering the two test polygons so the run is quick.
  win <- terra::ext(-100, 20, 22, 42)
  gdp_f <- tempfile(fileext = ".tif")
  pop_f <- tempfile(fileext = ".tif")
  terra::writeRaster(terra::crop(terra::rast(km$gdp_rast_path), win), gdp_f)
  terra::writeRaster(terra::crop(terra::rast(km$pop_rast_path), win), pop_f)
  km$gdp_rast_path <- gdp_f
  km$pop_rast_path <- pop_f

  box <- function(xmin, xmax, ymin, ymax) {
    sf::st_polygon(list(rbind(
      c(xmin, ymin), c(xmax, ymin), c(xmax, ymax),
      c(xmin, ymax), c(xmin, ymin)
    )))
  }
  ir <- sf::st_sf(
    hierid = c("USA.box", "DZA.box"),
    geometry = sf::st_sfc(box(-100, -95, 38, 42), box(15, 20, 22, 26),
                          crs = 4326)
  )
  cfg$paths$cache <- tempfile("aggtest")
  dir.create(cfg$paths$cache)

  res <- aggregate_kummu_to_ir(km, ir, cfg)

  g <- as.data.frame(res$gdppc)
  expect_setequal(colnames(g), c("hierid", "iso3", "year", "gdppc", "zero_pop"))
  expect_setequal(unique(g$iso3), c("USA", "DZA"))
  expect_equal(range(g$year), c(1990L, 2022L))
  expect_type(g$zero_pop, "logical")
  expect_true(all(as.data.frame(res$pop)$pop >= 0))
  expect_true(all(as.data.frame(res$density)$pop_wtd_density >= 0))
  expect_true(all(c("ratio", "pct_diff") %in%
                    colnames(as.data.frame(res$validation))))
  expect_true(file.exists(file.path(cfg$paths$cache, "ir_gdppc_kummu.csv")))
})
