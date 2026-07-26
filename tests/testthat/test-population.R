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

test_that("pop_control UN_WPP scales IRs to the UN WPP national totals", {
  skip_if_not(requireNamespace("readxl", quietly = TRUE))
  skip_if_not(requireNamespace("countrycode", quietly = TRUE))
  cfg <- io_setup()
  root <- find_repo_root()
  cfg$paths$cache <- file.path(root, cfg$paths$cache)
  sys.source(file.path(root, "R", "population.R"), envir = environment())
  skip_if_not(file.exists(file.path(cfg$paths$cache, "ir_pop_ghs.csv")),
              "aggregation cache not present")

  cfg$deltas$pop_control <- "UN_WPP"
  pop <- build_population(cfg, "SSP3")
  expect_equal(range(pop$year), c(1981L, 2100L))

  # IR populations sum to the WPP national total (persons) where WPP covers
  # the country.
  wpp <- read_wpp(cfg)
  sums <- pop[, .(ir_sum = sum(pop)), by = .(iso3, year)]
  chk <- merge(sums, wpp[, .(iso3, year, wpp_nat = pop * 1e6)],
               by = c("iso3", "year"))
  expect_gt(nrow(chk), 20000)
  expect_lt(max(abs(chk$ir_sum - chk$wpp_nat) / chk$wpp_nat), 1e-9)

  # The toggle changes the projection: totals differ from the IIASA control.
  cfg$deltas$pop_control <- "IIASA"
  pop_iiasa <- build_population(cfg, "SSP3")
  w <- pop[year == 2100, sum(pop)]
  i <- pop_iiasa[year == 2100, sum(pop)]
  expect_false(isTRUE(all.equal(w, i)))
})

test_that("build_population rejects an unknown pop_control", {
  cfg <- io_setup()
  root <- find_repo_root()
  sys.source(file.path(root, "R", "population.R"), envir = environment())
  cfg$deltas$pop_control <- "bogus"
  expect_error(build_population(cfg, "SSP3"), "unknown pop_control")
})
