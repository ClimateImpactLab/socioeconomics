# Input readers: one function per raw source, each returning a tidy in-memory
# object for the pipeline. Paths resolve from config (config.yml); ir_shapes and
# benchmark are read-only absolute paths on the shared volume.

#' Read Penn World Table 11.0 national GDP per capita (rgdpe / pop, 2021 USD PPP).
#'
#' @param config Parsed config.yml list.
#' @return data.table(iso3, year, gdppc_pwt).
read_pwt <- function(config) {
  stop("not implemented")
}

#' Read the IIASA SSP release 3.0 driver database (GDP, population, age cohorts).
#'
#' @param config Parsed config.yml list.
#' @return data.table(model, scenario, iso3, variable, unit, year, value).
read_ssp <- function(config) {
  # TODO(Phase 1): the input is the SSP 3.0 full xlsx, not the two CSV snapshots
  # the book used. Sheet layout, model/variable/scenario naming, units, and year
  # columns all differ, so this needs a 3.0-schema reader; do not assume the
  # book's column names.
  stop("not implemented")
}

#' Read Kummu et al. (2025) GDP-pc raster, GHS-POP raster, and ADM0 table.
#'
#' @param config Parsed config.yml list.
#' @return list(gdp_rast, pop_rast, adm0).
read_kummu <- function(config) {
  stop("not implemented")
}

#' Read UN WPP 2024 national population, the Delta #1 control totals.
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

#' Read the Carleton benchmark panel for validation.
#'
#' @param config Parsed config.yml list.
#' @return benchmark handle / data.table.
read_benchmark <- function(config) {
  # Benchmark is a Zarr store (integration-econ-bc39.zarr), not the book's
  # CIL_Socioecon.nc, so it needs Zarr-capable reading (a Python bridge in a
  # later phase).
  stop("not implemented")
}
