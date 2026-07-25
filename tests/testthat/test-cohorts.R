# Tests for R/cohorts.R. Runs build_cohorts against the cached aggregation and
# the real readers; skips if the cache is absent.

test_that("build_cohorts builds IR age-cohort populations over 1981-2100", {
  skip_if_not(requireNamespace("readxl", quietly = TRUE))
  skip_if_not(requireNamespace("countrycode", quietly = TRUE))
  cfg <- io_setup()
  root <- find_repo_root()
  cfg$paths$cache <- file.path(root, cfg$paths$cache)
  sys.source(file.path(root, "R", "population.R"), envir = environment())
  sys.source(file.path(root, "R", "cohorts.R"), envir = environment())
  skip_if_not(file.exists(file.path(cfg$paths$cache, "ir_pop_ghs.csv")),
              "aggregation cache not present")

  co <- as.data.frame(build_cohorts(cfg, "SSP3"))
  expect_setequal(colnames(co),
                  c("hierid", "iso3", "year", "scenario",
                    "pop0to4", "pop5to64", "pop65plus"))
  expect_equal(range(co$year), c(1981L, 2100L))
  expect_true(all(co$pop0to4 >= 0 & co$pop5to64 >= 0 & co$pop65plus >= 0))
})
