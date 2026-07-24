# Tests for R/io.R. Runs read_ssp against the real source files, skipping when
# they or the required packages are absent.

find_repo_root <- function() {
  d <- normalizePath(getwd())
  for (i in 1:6) {
    if (file.exists(file.path(d, "config.yml")) &&
        file.exists(file.path(d, "R", "io.R"))) {
      return(d)
    }
    d <- dirname(d)
  }
  NULL
}

test_that("read_ssp returns three ISO3-keyed parts from the real files", {
  skip_if_not(requireNamespace("yaml", quietly = TRUE))
  skip_if_not(requireNamespace("readxl", quietly = TRUE))
  skip_if_not(requireNamespace("countrycode", quietly = TRUE))
  skip_if_not(requireNamespace("data.table", quietly = TRUE))

  root <- find_repo_root()
  skip_if(is.null(root), "repo root not found")

  cfg <- yaml::read_yaml(file.path(root, "config.yml"))
  cfg$paths$source <- file.path(root, cfg$paths$source)
  xlsx <- file.path(cfg$paths$source, cfg$inputs$ssp)
  hist <- file.path(cfg$paths$source, cfg$inputs$ssp_hist)
  skip_if_not(file.exists(xlsx) && file.exists(hist),
              "SSP source files not present")

  source(file.path(root, "R", "io.R"), local = TRUE)
  ssp <- read_ssp(cfg)

  expect_setequal(names(ssp), c("gdppc", "pop", "cohorts"))

  gd <- as.data.frame(ssp$gdppc)
  expect_setequal(colnames(gd), c("model", "scenario", "iso3", "year", "gdppc"))
  expect_setequal(unique(gd$model), c("OECD", "IIASA"))
  expect_true(all(nchar(gd$iso3) == 3))
  expect_false(anyNA(gd$iso3))
  # OECD carries history back to 1980; IIASA per capita starts at 2025.
  expect_equal(min(gd$year), 1980L)
  expect_equal(min(gd$year[gd$model == "IIASA"]), 2025L)

  pop <- as.data.frame(ssp$pop)
  expect_setequal(unique(pop$era), c("historical", "projection"))
  expect_false(anyNA(pop$iso3))
  expect_true(all(pop$pop >= 0))

  coh <- as.data.frame(ssp$cohorts)
  expect_true(all(c("age0to4", "age5to64", "age65plus") %in% colnames(coh)))
  expect_true(all(coh$age0to4 >= 0 & coh$age5to64 >= 0 & coh$age65plus >= 0))

  # Cohorts sum close to total population for a projection slice.
  ps <- pop[pop$era == "projection" & pop$scenario == "SSP2" & pop$year == 2050,
            c("iso3", "pop")]
  cs <- coh[coh$era == "projection" & coh$scenario == "SSP2" &
              coh$year == 2050, ]
  cs$csum <- cs$age0to4 + cs$age5to64 + cs$age65plus
  m <- merge(ps, cs[, c("iso3", "csum")], by = "iso3")
  expect_lt(max(abs(m$pop - m$csum)), 1)
})
