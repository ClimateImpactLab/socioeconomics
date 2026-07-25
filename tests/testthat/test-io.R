# Tests for R/io.R. Each reader runs against the real source files and skips
# when the files or the required packages are absent. Shared setup
# (find_repo_root, io_setup) lives in helper-setup.R.

test_that("read_ssp returns three ISO3-keyed parts from the real files", {
  skip_if_not(requireNamespace("countrycode", quietly = TRUE))
  cfg <- io_setup()
  skip_if_not(
    file.exists(file.path(cfg$paths$source, cfg$inputs$ssp_snap_proj)) &&
      file.exists(file.path(cfg$paths$source, cfg$inputs$ssp_snap_hist)),
    "SSP source files not present"
  )

  ssp <- read_ssp(cfg)
  expect_setequal(names(ssp), c("gdppc", "pop", "cohorts"))

  gd <- as.data.frame(ssp$gdppc)
  expect_setequal(colnames(gd), c("model", "scenario", "iso3", "year", "gdppc"))
  expect_setequal(unique(gd$model), c("OECD", "IIASA"))
  expect_true(all(nchar(gd$iso3) == 3))
  expect_false(anyNA(gd$iso3))
  # IIASA per capita starts at 2025 in the SSP snapshot.
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

test_that("read_pwt returns national gdppc keyed on iso3 and year", {
  skip_if_not(requireNamespace("readxl", quietly = TRUE))
  cfg <- io_setup()
  skip_if_not(file.exists(file.path(cfg$paths$source, cfg$inputs$pwt)),
              "PWT file not present")

  pwt <- as.data.frame(read_pwt(cfg))
  expect_setequal(colnames(pwt), c("iso3", "year", "gdppc"))
  expect_true(all(nchar(pwt$iso3) == 3))
  expect_false(anyNA(pwt$iso3))
  expect_true(all(pwt$gdppc > 0))
  usa <- pwt$gdppc[pwt$iso3 == "USA" & pwt$year == 2019]
  expect_true(usa > 40000 && usa < 100000)
})

test_that("read_kummu returns an adm0 table and raster paths", {
  cfg <- io_setup()
  paths <- file.path(cfg$paths$source,
                     c(cfg$inputs$kummu_adm0, cfg$inputs$kummu_gdp_rast,
                       cfg$inputs$kummu_pop_rast))
  skip_if_not(all(file.exists(paths)), "Kummu files not present")

  km <- read_kummu(cfg)
  expect_setequal(names(km), c("adm0", "gdp_rast_path", "pop_rast_path"))
  adm0 <- as.data.frame(km$adm0)
  expect_setequal(colnames(adm0), c("iso3", "year", "gdppc"))
  expect_true(all(nchar(adm0$iso3) == 3))
  expect_true(all(adm0$year >= 1990 & adm0$year <= 2022))
  expect_true(file.exists(km$gdp_rast_path))
  expect_true(file.exists(km$pop_rast_path))
})

test_that("read_wpp returns national population keyed on iso3 and year", {
  skip_if_not(requireNamespace("readxl", quietly = TRUE))
  cfg <- io_setup()
  skip_if_not(file.exists(file.path(cfg$paths$source, cfg$inputs$wpp)),
              "WPP file not present")

  wpp <- as.data.frame(read_wpp(cfg))
  expect_setequal(colnames(wpp), c("iso3", "year", "pop"))
  expect_true(all(nchar(wpp$iso3) == 3))
  expect_true(all(wpp$pop > 0))
  expect_true(min(wpp$year) <= 1950 && max(wpp$year) >= 2100)
  expect_equal(anyDuplicated(wpp[, c("iso3", "year")]), 0L)
  usa <- wpp$pop[wpp$iso3 == "USA" & wpp$year == 2020]
  expect_true(usa > 300 && usa < 360)
})

test_that("read_ir_shapes returns valid IR polygons in WGS84", {
  skip_if_not(requireNamespace("sf", quietly = TRUE))
  cfg <- io_setup()
  skip_if_not(file.exists(cfg$paths$ir_shapes), "IR shapefile not present")

  shp <- read_ir_shapes(cfg)
  expect_s3_class(shp, "sf")
  expect_true("hierid" %in% names(shp))
  expect_equal(sf::st_crs(shp)$epsg, 4326L)
  expect_gt(nrow(shp), 24000)
})
