# Tests for R/postprocess.R. Assembles the panel from the cache, readers, and
# shapefile; skips if the cache or the shapefile is absent.

test_that("postprocess_panel assembles the ir_combined data columns", {
  skip_if_not(requireNamespace("readxl", quietly = TRUE))
  skip_if_not(requireNamespace("countrycode", quietly = TRUE))
  skip_if_not(requireNamespace("sf", quietly = TRUE))
  cfg <- io_setup()
  root <- find_repo_root()
  cfg$paths$cache <- file.path(root, cfg$paths$cache)
  for (mod in c("income", "population", "cohorts", "postprocess")) {
    sys.source(file.path(root, "R", paste0(mod, ".R")), envir = environment())
  }
  skip_if_not(file.exists(file.path(cfg$paths$cache, "ir_gdppc_kummu.csv")),
              "aggregation cache not present")
  skip_if_not(file.exists(cfg$paths$ir_shapes), "IR shapefile not present")

  p <- as.data.frame(postprocess_panel(cfg, "SSP3", "IIASA"))
  expect_setequal(colnames(p),
                  c("hierid", "iso3", "year", "gdppc", "gdppc_raw",
                    "gdppc_raw0", "gdp", "pop", "area_km2", "pop_density",
                    "pop_wtd_density", "pop0to4", "pop5to64", "pop65plus"))
  expect_equal(range(p$year), c(1981L, 2100L))
  expect_true(all(p$gdppc >= 0 & p$gdp >= 0 & p$pop >= 0))
})
