# Input readers: one function per raw source, each returning a tidy in-memory
# object for the pipeline. Paths resolve from config (config.yml); ir_shapes and
# benchmark are read-only absolute paths on the shared volume.

#' Read Penn World Table 11.0 national GDP per capita (rgdpe / pop, 2021 PPP).
#'
#' @param config Parsed config.yml list.
#' @return data.table(iso3, year, gdppc). PWT already carries ISO3 codes.
read_pwt <- function(config) {
  d <- data.table::as.data.table(
    readxl::read_excel(file.path(config$paths$source, config$inputs$pwt),
                       sheet = "Data")
  )
  out <- d[!is.na(rgdpe) & !is.na(pop) & pop > 0,
           .(iso3 = countrycode, year = as.integer(year),
             gdppc = rgdpe / pop)]
  out[!is.na(iso3)][order(iso3, year)]
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

# Melt a wide SSP table (Model/Scenario/Region/Variable/Unit then year columns)
# to long form keyed on iso3, dropping the copyright footer row if present.
ssp_wide_to_long <- function(wide) {
  id_cols <- c("model", "scenario", "region", "variable", "unit")
  data.table::setnames(wide, names(wide)[1:5], id_cols)
  wide <- wide[!startsWith(as.character(model), "©")]
  year_cols <- grep("^[0-9]{4}$", names(wide), value = TRUE)
  wide[, (year_cols) := lapply(.SD, as.numeric), .SDcols = year_cols]
  long <- data.table::melt(wide, id.vars = id_cols, measure.vars = year_cols,
                           variable.name = "year", value.name = "value")
  long[, year := as.integer(as.character(year))]
  ssp_regions_to_iso3(long[!is.na(value)])
}

# Read a wide SSP snapshot CSV. The files carry a byte-order mark that otherwise
# leaves the real header as the first data row; recover it when that happens.
read_ssp_wide_csv <- function(path) {
  d <- data.table::fread(path)
  if (!"Model" %in% names(d)) {
    data.table::setnames(d, as.character(unlist(d[1])))
    d <- d[-1]
  }
  d
}

#' Read national SSP GDP, population, and age cohorts, keyed on ISO3.
#'
#' @param config Parsed config.yml list. options$ssp_source picks the input:
#'   "snapshots" (the reference's SSP snapshot CSVs) or "xlsx" (release 3.0).
#' @return list with three data.tables: gdppc (model, scenario, iso3, year,
#'   gdppc in 2017 PPP USD), pop (era, scenario, iso3, year, pop in millions),
#'   cohorts (era, scenario, iso3, year, age0to4, age5to64, age65plus in
#'   millions). era is "historical" or "projection".
read_ssp <- function(config) {
  src <- config$paths$source
  mode <- if (is.null(config$options$ssp_source)) "xlsx" else
    config$options$ssp_source

  if (mode == "snapshots") {
    # Two snapshot CSVs: projections (2020-2100) and historical (1950-2020).
    proj <- ssp_wide_to_long(
      read_ssp_wide_csv(file.path(src, config$inputs$ssp_snap_proj)))
    hist <- ssp_wide_to_long(
      read_ssp_wide_csv(file.path(src, config$inputs$ssp_snap_hist)))
  } else {
    # Release 3.0: projections in the xlsx, history in a separate long csv.
    proj <- ssp_wide_to_long(data.table::as.data.table(
      readxl::read_excel(file.path(src, config$inputs$ssp), sheet = "data")))
    hist <- ssp_regions_to_iso3(
      data.table::fread(file.path(src, config$inputs$ssp_hist))[!is.na(value)])
  }

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

#' Read Kummu et al. (2025) national GDP per capita and the raster paths.
#'
#' @param config Parsed config.yml list.
#' @return list with adm0 (data.table iso3, year, gdppc) and gdp_rast_path /
#'   pop_rast_path (file paths; the rasters are not loaded here).
read_kummu <- function(config) {
  src <- config$paths$source
  wide <- data.table::fread(file.path(src, config$inputs$kummu_adm0))
  year_cols <- grep("^[0-9]{4}$", names(wide), value = TRUE)
  adm0 <- data.table::melt(wide, id.vars = "iso3", measure.vars = year_cols,
                           variable.name = "year", value.name = "gdppc")
  adm0[, year := as.integer(as.character(year))]
  adm0 <- adm0[!is.na(iso3) & iso3 != "" & !is.na(gdppc), .(iso3, year, gdppc)]
  list(
    adm0          = adm0[order(iso3, year)],
    gdp_rast_path = normalizePath(file.path(src, config$inputs$kummu_gdp_rast)),
    pop_rast_path = normalizePath(file.path(src, config$inputs$kummu_pop_rast))
  )
}

# Read one WPP sheet (Estimates or Medium variant). The data starts a few rows
# below a header block, so the header row is found by its "ISO3 Alpha-code"
# label rather than a fixed offset. Country rows are Type "Country/Area";
# regional groupings and the World total are dropped. Population is the mid-year
# (1 July) total, converted from thousands to millions.
read_wpp_sheet <- function(path, sheet) {
  raw <- data.table::as.data.table(
    readxl::read_excel(path, sheet = sheet, col_names = FALSE,
                       .name_repair = "minimal")
  )
  hdr <- which(vapply(
    seq_len(nrow(raw)),
    function(i) any(raw[i] == "ISO3 Alpha-code", na.rm = TRUE),
    logical(1)
  ))[1]
  h <- as.character(unlist(raw[hdr]))
  col <- function(label) which(h == label)[1]
  body <- raw[(hdr + 1):.N]
  # Rows below the country data (notes, blanks) do not coerce to number; they
  # become NA here and are dropped by the filter below.
  out <- suppressWarnings(data.table::data.table(
    iso3 = as.character(body[[col("ISO3 Alpha-code")]]),
    type = as.character(body[[col("Type")]]),
    year = as.integer(body[[col("Year")]]),
    pop  = as.numeric(
      body[[col("Total Population, as of 1 July (thousands)")]]
    ) / 1e3
  ))
  out[type == "Country/Area" & !is.na(iso3) & !is.na(year), .(iso3, year, pop)]
}

#' Read UN WPP 2024 national population totals, keyed on ISO3 (millions).
#'
#' @param config Parsed config.yml list.
#' @return data.table(iso3, year, pop) over estimates and the medium variant.
read_wpp <- function(config) {
  path <- file.path(config$paths$source, config$inputs$wpp)
  both <- data.table::rbindlist(list(
    read_wpp_sheet(path, "Estimates"),
    read_wpp_sheet(path, "Medium variant")
  ))
  # Estimates end at 2023 and the medium variant begins at 2024; keep the
  # estimate if any year appears in both.
  data.table::setorder(both, iso3, year)
  unique(both, by = c("iso3", "year"))
}

#' Read the impact-region polygons, assigning WGS84 if the CRS is missing.
#'
#' @param config Parsed config.yml list.
#' @return sf polygons keyed on hierid.
read_ir_shapes <- function(config) {
  shp <- sf::st_read(config$paths$ir_shapes, quiet = TRUE)
  if (is.na(sf::st_crs(shp))) {
    sf::st_crs(shp) <- 4326
  }
  shp <- sf::st_make_valid(shp)
  message("read_ir_shapes: ", nrow(shp), " polygons")
  shp
}

#' Read the benchmark panel, converting the Zarr store to a cached CSV first.
#'
#' @param config Parsed config.yml list.
#' @return data.table(region, model, ssp, year, gdp, gdppc, pop).
read_benchmark <- function(config) {
  out <- file.path(config$paths$cache, "benchmark.csv.gz")
  if (!file.exists(out)) {
    # No dependable Zarr reader in R, so a Python helper writes the store to a
    # cached CSV once. It needs a Python with xarray and zarr; override the
    # executable with the PYTHON environment variable if needed.
    if (!dir.exists(config$paths$cache)) {
      dir.create(config$paths$cache, recursive = TRUE)
    }
    py <- Sys.getenv("PYTHON", unset = "python")
    message("read_benchmark: converting Zarr store to ", out)
    status <- system2(py, c(
      shQuote(file.path("data", "benchmark_to_csv.py")),
      shQuote(config$paths$benchmark), shQuote(out)
    ))
    if (status != 0 || !file.exists(out)) {
      stop("benchmark conversion failed; need a Python with xarray and zarr")
    }
  }
  data.table::fread(out)
}
