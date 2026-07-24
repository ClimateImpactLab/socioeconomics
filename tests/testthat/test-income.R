# Tests for R/income.R. Runs build_income against the cached aggregation and the
# real readers; skips if the cache or the SSP input is absent.

test_that("build_income builds an IR gdppc panel over 1990-2100", {
  skip_if_not(requireNamespace("readxl", quietly = TRUE))
  skip_if_not(requireNamespace("countrycode", quietly = TRUE))
  cfg <- io_setup()
  root <- find_repo_root()
  cfg$paths$cache <- file.path(root, cfg$paths$cache)
  sys.source(file.path(root, "R", "income.R"), envir = environment())

  cache_csv <- file.path(cfg$paths$cache, "ir_gdppc_kummu.csv")
  skip_if_not(file.exists(cache_csv), "aggregation cache not present")
  skip_if_not(file.exists(file.path(cfg$paths$source, cfg$inputs$ssp)),
              "SSP input not present")

  inc <- as.data.frame(build_income(cfg, "SSP3", "IIASA"))
  expect_setequal(
    colnames(inc),
    c("hierid", "iso3", "year", "scenario", "gdp_model", "gdppc")
  )
  expect_equal(range(inc$year), c(1990L, 2100L))
  expect_true(all(inc$scenario == "SSP3"))
  expect_true(all(inc$gdp_model == "IIASA"))
  expect_true(all(inc$gdppc[!is.na(inc$gdppc)] > 0))
  expect_equal(length(unique(inc$year)), 111L)
})
