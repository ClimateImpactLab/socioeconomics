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

test_that("pop_control UN_WPP follows WPP to the handoff, then rebased SSP", {
  skip_if_not(requireNamespace("readxl", quietly = TRUE))
  skip_if_not(requireNamespace("countrycode", quietly = TRUE))
  cfg <- io_setup()
  root <- find_repo_root()
  cfg$paths$cache <- file.path(root, cfg$paths$cache)
  sys.source(file.path(root, "R", "population.R"), envir = environment())
  skip_if_not(file.exists(file.path(cfg$paths$cache, "ir_pop_ghs.csv")),
              "aggregation cache not present")

  cfg$deltas$pop_control <- "UN_WPP"
  cfg$deltas$pop_handoff_year <- 2023
  pop <- build_population(cfg, "SSP3")
  expect_equal(range(pop$year), c(1981L, 2100L))

  # Through the handoff the IR sums match the WPP national totals.
  wpp <- read_wpp(cfg)
  s3 <- pop[, .(ir_sum = sum(pop)), by = .(iso3, year)]
  chk <- merge(s3[year <= 2023], wpp[, .(iso3, year, wpp_nat = pop * 1e6)],
               by = c("iso3", "year"))
  expect_gt(nrow(chk), 5000)
  expect_lt(max(abs(chk$ir_sum - chk$wpp_nat) / chk$wpp_nat), 1e-9)

  # After the handoff the scenario matters: SSP2 equals SSP3 at the handoff
  # and differs from it by 2100.
  s2 <- build_population(cfg, "SSP2")[, .(ir_sum = sum(pop)),
                                      by = .(iso3, year)]
  expect_equal(s2[year == 2023][order(iso3), ir_sum],
               s3[year == 2023][order(iso3), ir_sum])
  expect_false(isTRUE(all.equal(s2[year == 2100, sum(ir_sum)],
                                s3[year == 2100, sum(ir_sum)])))

  # No jump at the seam: India's 2023 -> 2024 growth equals the SSP's.
  ssp_ann <- pop_linear_annual(read_ssp(cfg)$pop[
    era == "projection" & scenario == "SSP3", .(iso3, year, nat = pop)])
  g_ssp <- ssp_ann[iso3 == "IND" & year %in% c(2023, 2024)][order(year), nat]
  g_pan <- s3[iso3 == "IND" & year %in% c(2023, 2024)][order(year), ir_sum]
  expect_lt(abs(g_pan[2] / g_pan[1] - g_ssp[2] / g_ssp[1]), 1e-9)
})

test_that("build_population rejects an unknown pop_control", {
  cfg <- io_setup()
  root <- find_repo_root()
  sys.source(file.path(root, "R", "population.R"), envir = environment())
  cfg$deltas$pop_control <- "bogus"
  expect_error(build_population(cfg, "SSP3"), "unknown pop_control")
})
