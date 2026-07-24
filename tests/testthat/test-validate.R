# Tests for R/validate.R. The reader-vs-reader comparison runs against the real
# files; the reference-based comparisons skip until the reference panel is
# present. Shared setup lives in helper-setup.R.

test_that("compare_pop_sources returns one row per iso3-year", {
  skip_if_not(requireNamespace("readxl", quietly = TRUE))
  skip_if_not(requireNamespace("countrycode", quietly = TRUE))
  cfg <- io_setup()
  skip_if_not(
    file.exists(file.path(cfg$paths$source, cfg$inputs$wpp)) &&
      file.exists(file.path(cfg$paths$source, cfg$inputs$ssp)),
    "WPP or SSP file not present"
  )

  cmp <- as.data.frame(compare_pop_sources(cfg, "SSP3"))
  expect_setequal(
    colnames(cmp),
    c("iso3", "year", "pop_wpp", "pop_ssp", "ratio", "pct_diff")
  )
  expect_equal(anyDuplicated(cmp[, c("iso3", "year")]), 0L)
  expect_true(all(cmp$pop_wpp > 0 & cmp$pop_ssp > 0))
})

test_that("reference_national aggregates the panel to national level", {
  cfg <- io_setup()
  skip_if_not(file.exists(file.path(cfg$paths$source, cfg$inputs$reference)),
              "reference panel not present")

  rn <- as.data.frame(reference_national(cfg))
  expect_setequal(
    colnames(rn),
    c("iso3", "year", "pop_nat", "gdppc_nat",
      "share_0_4", "share_5_64", "share_65plus")
  )
  expect_true(all(rn$pop_nat > 0 & rn$gdppc_nat > 0))
  shares <- rn$share_0_4 + rn$share_5_64 + rn$share_65plus
  expect_lt(max(abs(shares - 1)), 0.01)
})

test_that("compare_income_pwt deflates PWT and flags known divergences", {
  skip_if_not(requireNamespace("readxl", quietly = TRUE))
  cfg <- io_setup()
  skip_if_not(
    file.exists(file.path(cfg$paths$source, cfg$inputs$reference)) &&
      file.exists(file.path(cfg$paths$source, cfg$inputs$pwt)),
    "reference or PWT file not present"
  )

  ci <- as.data.frame(compare_income_pwt(cfg))
  expect_true(all(c("gdppc_ref", "gdppc_pwt", "growth_ref", "growth_pwt",
                    "ratio", "pct_diff", "flag") %in% colnames(ci)))
  expect_true(all(ci$flag %in% c("", "venezuela", "no_pwt")))
})

test_that("compare_cohorts_ssp compares national age shares", {
  skip_if_not(requireNamespace("readxl", quietly = TRUE))
  skip_if_not(requireNamespace("countrycode", quietly = TRUE))
  cfg <- io_setup()
  skip_if_not(
    file.exists(file.path(cfg$paths$source, cfg$inputs$reference)) &&
      file.exists(file.path(cfg$paths$source, cfg$inputs$ssp)),
    "reference or SSP file not present"
  )

  cc <- as.data.frame(compare_cohorts_ssp(cfg, "SSP3"))
  expect_true(all(c("diff_0_4", "diff_5_64", "diff_65plus") %in% colnames(cc)))
})
