# Tests for R/checks.R: a synthetic mini-panel that satisfies every contract,
# then targeted mutations that must each trip their check. The synthetic grid
# patches N_IR/YEARS so the structural checks scale down.

library(data.table)

make_panel <- function(n_ir = 3, years = 2019:2021) {
  grid <- CJ(hierid = sprintf("AAA.%d", seq_len(n_ir)), year = years)
  p <- grid[, .(
    hierid, iso3 = "AAA", year,
    gdppc = 1000, gdppc_raw = 1000, gdppc_raw0 = 1000,
    pop = 50, area_km2 = 10, pop_wtd_density = 5,
    pop0to4 = 5, pop5to64 = 40, pop65plus = 5
  )]
  p[, gdp := gdppc * pop]
  p[, pop_density := pop / area_km2]
  setcolorder(p, c("hierid", "iso3", "year", "gdppc", "gdppc_raw",
                   "gdppc_raw0", "gdp", "pop", "area_km2", "pop_density",
                   "pop_wtd_density", "pop0to4", "pop5to64", "pop65plus"))
  p
}

check_env <- function(n_ir = 3, years = 2019:2021) {
  root <- find_repo_root()
  e <- new.env()
  sys.source(file.path(root, "R", "checks.R"), envir = e)
  assign("N_IR", as.integer(n_ir), envir = e)
  assign("YEARS", years, envir = e)
  e
}

cfg <- list(deltas = list(pop_control = "IIASA", force_gdp_sum = FALSE),
            tolerances = list(gdp_sum_pct = 0.1))

test_that("a well-formed panel passes every check", {
  e <- check_env()
  expect_silent(suppressMessages(
    e$check_panel(make_panel(), cfg, "SSP3", "IIASA")))
})

test_that("each contract violation is caught", {
  e <- check_env()
  run <- function(p) suppressMessages(
    e$check_panel(p, cfg, "SSP3", "IIASA"))

  p <- make_panel()
  p[1, pop := NA_real_]
  expect_error(run(p), "no_unexpected_na")

  p <- make_panel()
  p <- rbind(p, p[1])
  expect_error(run(p), "no_duplicates")

  p <- make_panel()[-1]
  expect_error(run(p), "grid_size")

  p <- make_panel()
  p[2, gdppc_raw := NA_real_]  # NA after data begins, gdppc nonzero
  expect_error(run(p), "raw_na_only_deliberate")

  p <- make_panel()
  p[1, gdppc := -5]
  p[1, gdp := gdppc * pop]
  expect_error(run(p), "gdppc_band")

  p <- make_panel()
  p[, pop0to4 := pop0to4 * 3]  # breaks the cohort band
  expect_error(run(p), "cohorts_sum_to_pop")

  p <- make_panel()
  p[1, gdp := gdp * 2]
  expect_error(run(p), "gdp_is_gdppc_times_pop")
})

test_that("cross-panel checks catch model-dependent population", {
  e <- check_env()
  a <- make_panel()
  b <- make_panel()
  expect_silent(suppressMessages(e$check_cross_panel(
    list(SSP9_OECD = a, SSP9_IIASA = b), cfg)))
  b2 <- copy(b)[1, pop := pop + 1]
  expect_error(suppressMessages(e$check_cross_panel(
    list(SSP9_OECD = a, SSP9_IIASA = b2), cfg)), "pop_model_independent")
  b3 <- copy(b)[1, area_km2 := area_km2 + 1]
  expect_error(suppressMessages(e$check_cross_panel(
    list(SSP9_OECD = a, SSP9_IIASA = b3), cfg)), "area_identical")
})

test_that("cross-panel checks catch scenario-independent population", {
  e <- check_env()
  cfg2 <- modifyList(cfg, list(deltas = list(pop_handoff_year = 2019)))
  a <- make_panel()  # years 2019:2021, so 2020-2021 are post-handoff
  expect_error(suppressMessages(e$check_cross_panel(
    list(SSP2_OECD = a, SSP3_OECD = make_panel()), cfg2)),
    "pop_differs_across_scenarios")
  b <- copy(a)[year > 2019, pop := pop + 1]
  expect_silent(suppressMessages(e$check_cross_panel(
    list(SSP2_OECD = a, SSP3_OECD = b), cfg2)))
})
