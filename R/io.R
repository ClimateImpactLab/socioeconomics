# Input readers: one function per raw source, each returning a tidy in-memory
# object for the pipeline. Paths resolve from config (config.yml); ir_shapes and
# benchmark are read-only absolute paths on the shared volume.

#' Read Penn World Table 11.0 national GDP per capita (rgdpe / pop, 2021 PPP).
#'
#' @param config Parsed config.yml list.
#' @return data.table(iso3, year, gdppc_pwt).
read_pwt <- function(config) {
  stop("not implemented")
}

# Map SSP region names to ISO3, dropping the "World" and R5/R10 aggregates and
# any name that does not resolve. Aggregates are the "(R5)"/"(R9)"/"(R10)"
# suffix only; some real countries also carry parentheses, so they are kept.
# Curacao and Reunion are matched by prefix because their accented characters
# do not survive the read.
ssp_regions_to_iso3 <- function(dt) {
  dt <- dt[region != "World" & !grepl("\\(R[0-9]+\\)$", region)]
  regs <- unique(dt$region)
  exact <- c(Kosovo = "XKX", Taiwan = "TWN", Micronesia = "FSM")
  iso3 <- rep(NA_character_, length(regs))
  iso3[regs %in% names(exact)] <- exact[regs[regs %in% names(exact)]]
  iso3[grepl("^Cura", regs)] <- "CUW"
  iso3[grepl("^R.union$", regs)] <- "REU"
  need <- is.na(iso3)
  iso3[need] <- countrycode::countrycode(
    regs[need], "country.name", "iso3c", warn = FALSE
  )
  lut <- stats::setNames(iso3, regs)
  dt[, iso3 := lut[region]]
  unmapped <- sort(unique(dt[is.na(iso3), region]))
  if (length(unmapped) > 0) {
    message("read_ssp: dropping ", length(unmapped),
            " unmapped region(s): ", paste(unmapped, collapse = ", "))
  }
  dt[!is.na(iso3)]
}

# Sum male+female population into 0-4 / 5-64 / 65+ per scenario/iso/year. Only
# the two-pipe "Population|<sex>|Age <bin>" variables are used, which excludes
# both the education splits and the "Mean Years of Education" variables.
ssp_age_bins <- function(dt, era) {
  a <- dt[grepl("^Population\\|(Male|Female)\\|Age [^|]+$", variable)]
  a[, age_lower := as.integer(sub(".*\\|Age ([0-9]+).*", "\\1", variable))]
  a[, bin := data.table::fifelse(
    age_lower < 5, "age0to4",
    data.table::fifelse(age_lower < 65, "age5to64", "age65plus")
  )]
  b <- a[, .(value = sum(value, na.rm = TRUE)),
         by = .(scenario, iso3, year, bin)]
  w <- data.table::dcast(b, scenario + iso3 + year ~ bin,
                         value.var = "value", fill = 0)
  for (col in c("age0to4", "age5to64", "age65plus")) {
    if (!col %in% names(w)) w[[col]] <- 0
  }
  w[, era := era]
  w[, .(era, scenario, iso3, year, age0to4, age5to64, age65plus)]
}

#' Read national SSP GDP, population, and age cohorts, keyed on ISO3.
#'
#' @param config Parsed config.yml list.
#' @return list with three data.tables: gdppc (model, scenario, iso3, year,
#'   gdppc in 2017 PPP USD), pop (era, scenario, iso3, year, pop in millions),
#'   cohorts (era, scenario, iso3, year, age0to4, age5to64, age65plus in
#'   millions). era is "historical" or "projection".
read_ssp <- function(config) {
  src <- config$paths$source
  id_cols <- c("model", "scenario", "region", "variable", "unit")

  # Projection file: wide xlsx, years in columns.
  proj_wide <- data.table::as.data.table(
    readxl::read_excel(file.path(src, config$inputs$ssp), sheet = "data")
  )
  data.table::setnames(
    proj_wide,
    c("Model", "Scenario", "Region", "Variable", "Unit"), id_cols
  )
  year_cols <- grep("^[0-9]{4}$", names(proj_wide), value = TRUE)
  # Some year columns are all-NA and read as logical; coerce so melt keeps
  # a single type.
  proj_wide[, (year_cols) := lapply(.SD, as.numeric), .SDcols = year_cols]
  proj <- data.table::melt(
    proj_wide, id.vars = id_cols, measure.vars = year_cols,
    variable.name = "year", value.name = "value"
  )
  proj[, year := as.integer(as.character(year))]
  proj <- ssp_regions_to_iso3(proj[!is.na(value)])

  # History file: long csv, IIASA-WiC POP 2025, scenario "Historical Reference".
  hist <- data.table::fread(file.path(src, config$inputs$ssp_hist))
  hist <- ssp_regions_to_iso3(hist[!is.na(value)])

  # GDP per capita. OECD gives it directly; IIASA gives total GDP only, so its
  # per capita is total GDP divided by the IIASA-WiC POP 2023 population from
  # the same release (billion / million * 1e3 -> USD per person).
  oecd <- proj[model == "OECD ENV-Growth 2023" &
                 variable == "GDP|PPP [per capita]",
               .(model = "OECD", scenario, iso3, year, gdppc = value)]
  iiasa_gdp <- proj[model == "IIASA GDP 2023" & variable == "GDP|PPP",
                    .(scenario, iso3, year, gdp_bn = value)]
  iiasa_pop <- proj[model == "IIASA-WiC POP 2023" & variable == "Population",
                    .(scenario, iso3, year, pop_mn = value)]
  iiasa <- merge(iiasa_gdp, iiasa_pop, by = c("scenario", "iso3", "year"))
  iiasa <- iiasa[pop_mn > 0,
                 .(model = "IIASA", scenario, iso3, year,
                   gdppc = gdp_bn / pop_mn * 1e3)]
  gdppc <- data.table::rbindlist(list(oecd, iiasa))

  # National population, both eras (millions).
  pop_proj <- proj[model == "IIASA-WiC POP 2023" & variable == "Population",
                   .(era = "projection", scenario, iso3, year, pop = value)]
  pop_hist <- hist[variable == "Population",
                   .(era = "historical", scenario, iso3, year, pop = value)]
  pop <- data.table::rbindlist(list(pop_hist, pop_proj))

  # Age cohorts, both eras (millions).
  cohorts <- data.table::rbindlist(list(
    ssp_age_bins(hist, "historical"),
    ssp_age_bins(proj[model == "IIASA-WiC POP 2023"], "projection")
  ))

  list(
    gdppc   = gdppc[order(model, scenario, iso3, year)],
    pop     = pop[order(era, scenario, iso3, year)],
    cohorts = cohorts[order(era, scenario, iso3, year)]
  )
}

#' Read Kummu et al. (2025) GDP-pc raster, GHS-POP raster, and ADM0 table.
#'
#' @param config Parsed config.yml list.
#' @return list(gdp_rast, pop_rast, adm0).
read_kummu <- function(config) {
  stop("not implemented")
}

#' Read UN WPP 2024 national population used as the population control total.
#'
#' @param config Parsed config.yml list.
#' @return data.table(iso3, year, pop_wpp, ...).
read_wpp <- function(config) {
  stop("not implemented")
}

#' Read the impact-region polygons (~24,378 IRs), assigning WGS84 if unset.
#'
#' @param config Parsed config.yml list.
#' @return sf polygons keyed on hierid.
read_ir_shapes <- function(config) {
  stop("not implemented")
}

#' Read the benchmark panel for validation.
#'
#' @param config Parsed config.yml list.
#' @return benchmark handle / data.table.
read_benchmark <- function(config) {
  # Benchmark is a Zarr store (integration-econ-bc39.zarr), so it needs
  # Zarr-capable reading (a Python bridge in a later phase).
  stop("not implemented")
}
