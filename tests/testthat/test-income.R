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
  skip_if_not(file.exists(file.path(cfg$paths$source, cfg$inputs$ssp_snap_proj)),
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

test_that("force_gdp_sum scales IR GDP to the SSP national total", {
  skip_if_not(requireNamespace("readxl", quietly = TRUE))
  skip_if_not(requireNamespace("countrycode", quietly = TRUE))
  cfg <- io_setup()
  root <- find_repo_root()
  cfg$paths$cache <- file.path(root, cfg$paths$cache)
  sys.source(file.path(root, "R", "population.R"), envir = environment())
  sys.source(file.path(root, "R", "income.R"), envir = environment())

  cache_csv <- file.path(cfg$paths$cache, "ir_gdppc_kummu.csv")
  skip_if_not(file.exists(cache_csv), "aggregation cache not present")
  skip_if_not(file.exists(file.path(cfg$paths$source,
                                    cfg$inputs$ssp_snap_proj)),
              "SSP input not present")

  cfg$deltas$force_gdp_sum <- TRUE
  inc <- build_income(cfg, "SSP3", "IIASA")
  pop <- build_population(cfg, "SSP3")[, .(hierid, year, pop)]
  ssp_gdppc <- read_ssp(cfg)$gdppc[scenario == "SSP3"]
  nat <- interp_annual(ssp_gdppc[model == "IIASA", .(iso3, year, gdppc)])
  nat <- nat[year >= 2024, .(iso3, year, nat_gdppc = gdppc * KUMMU_TO_2005)]

  x <- merge(inc, pop, by = c("hierid", "year"))
  sums <- x[!is.na(gdppc) & pop > 0,
            .(ir_gdp = sum(gdppc * pop), pop_nat = sum(pop)),
            by = .(iso3, year)]
  chk <- merge(sums, nat, by = c("iso3", "year"))
  expect_gt(nrow(chk), 10000)
  expect_lt(max(abs(chk$ir_gdp - chk$nat_gdppc * chk$pop_nat)
                / (chk$nat_gdppc * chk$pop_nat)), 1e-9)

  # PWT-anchored years are untouched.
  cfg$deltas$force_gdp_sum <- FALSE
  inc_off <- build_income(cfg, "SSP3", "IIASA")
  pre <- merge(inc[year <= 2023, .(hierid, year, on = gdppc)],
               inc_off[year <= 2023, .(hierid, year, off = gdppc)],
               by = c("hierid", "year"))
  expect_identical(pre$on, pre$off)
})
