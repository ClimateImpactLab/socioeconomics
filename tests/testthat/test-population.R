# Tests for R/population.R. Runs build_population against the cached aggregation
# and the real readers; skips if the cache is absent.

test_that("build_population builds an IR population panel over 1981-2100", {
  skip_if_not(requireNamespace("readxl", quietly = TRUE))
  skip_if_not(requireNamespace("countrycode", quietly = TRUE))
  cfg <- io_setup()
  root <- find_repo_root()
  cfg$paths$cache <- file.path(root, cfg$paths$cache)
  sys.source(file.path(root, "R", "population.R"), envir = environment())
  skip_if_not(file.exists(file.path(cfg$paths$cache, "ir_pop_ghs.csv")),
              "aggregation cache not present")

  pop <- as.data.frame(build_population(cfg, "SSP3"))
  expect_setequal(colnames(pop),
                  c("hierid", "iso3", "year", "scenario", "pop"))
  expect_equal(range(pop$year), c(1981L, 2100L))
  expect_true(all(pop$scenario == "SSP3"))
  expect_true(all(pop$pop >= 0))
})
