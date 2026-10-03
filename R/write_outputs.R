# Serialize the combination panels into the canonical Zarr store. The store
# mirrors the benchmark layout (integration-econ-bc39.zarr) so it is a
# drop-in replacement: dims (ssp, region, model, year), float32 variables,
# model labels "IIASA GDP" / "OECD Env-Growth", plus the additional panel
# variables (raw income, cohorts, densities, area) new consumers can use.

#' Assemble the per-combination panel CSVs into one Zarr store.
#'
#' Zarr has no dependable R writer, so the serialization runs in Python
#' (data/panels_to_zarr.py), which needs pandas, numpy, xarray, and zarr;
#' the interpreter is resolved by resolve_python (io.R), overridable with
#' the PYTHON environment variable.
#'
#' @param config Parsed config.yml list.
#' @param panel_files Character vector of ir_combined_<scen>_<model>.csv
#'   paths, one per combination.
#' @return The store path, invisibly.
write_zarr <- function(config, panel_files) {
  out <- file.path(config$paths$output, "ir_combined.zarr")
  py <- resolve_python()
  status <- system2(py, c(
    shQuote(file.path("data", "panels_to_zarr.py")),
    shQuote(out),
    vapply(panel_files, shQuote, character(1))
  ))
  if (status != 0) {
    stop("panels_to_zarr.py failed with status ", status)
  }
  invisible(out)
}

# Branch and commit of the repo HEAD, read from .git directly so the writer
# works where no git binary is available (inside the container).
git_head_info <- function(gitdir = ".git") {
  head_path <- file.path(gitdir, "HEAD")
  if (!file.exists(head_path)) {
    return(list(branch = "unknown", commit = "unknown"))
  }
  head <- readLines(head_path, warn = FALSE)[1]
  if (!startsWith(head, "ref: ")) {
    return(list(branch = "detached", commit = head))
  }
  ref <- sub("^ref: ", "", head)
  commit <- "unknown"
  ref_file <- file.path(gitdir, ref)
  if (file.exists(ref_file)) {
    commit <- readLines(ref_file, warn = FALSE)[1]
  } else {
    packed <- file.path(gitdir, "packed-refs")
    if (file.exists(packed)) {
      hit <- grep(paste0(" ", ref, "$"), readLines(packed, warn = FALSE),
                  value = TRUE)
      if (length(hit) > 0) commit <- substr(hit[1], 1, 40)
    }
  }
  list(branch = basename(ref), commit = commit)
}

#' Write a plain-language provenance README.txt into the output folder.
#'
#' Records when the panel was generated, from which repo state (branch and
#' commit), with which config file and main settings, the input data versions
#' from data/manifest.yml, and an md5 for each panel CSV.
#'
#' @param config Parsed track config list.
#' @param config_path Path of the track config file.
#' @param panel_files Character vector of the panel CSV paths.
#' @param ... Upstream targets accepted only for dependency ordering.
#' @return The README.txt path, invisibly.
write_output_readme <- function(config, config_path, panel_files, ...) {
  git <- git_head_info()
  d <- config$deltas
  pop_line <- if (identical(d$pop_control, "UN_WPP")) {
    h <- d$pop_handoff_year
    if (is.null(h)) h <- 2023
    paste0("UN WPP 2024 national totals through ", h, ", then each SSP's\n",
           "  own trajectory rebased to the WPP level at ", h,
           " (no jump at the seam).")
  } else {
    "IIASA-WiC SSP national totals in every year (the book reproduction)."
  }
  manifest <- yaml::read_yaml(file.path("data", "manifest.yml"))
  versions <- vapply(names(manifest$sources), function(nm) {
    paste0("  - ", nm, ": ", manifest$sources[[nm]]$version)
  }, character(1))
  md5s <- tools::md5sum(panel_files)
  file_lines <- paste0("  ", format(basename(panel_files)), "  ", md5s)

  lines <- c(
    "Impact-region socioeconomic panel",
    "=================================",
    "",
    paste0("Generated: ", format(Sys.time(), "%Y-%m-%d %H:%M %Z")),
    paste0("Pipeline: socioeconomics-update panel pipeline (irpanel), branch ",
           git$branch, ", commit ", git$commit),
    paste0("Config: ", config_path),
    if (!is.null(config$version)) paste0("Version: ", config$version),
    "",
    "Main settings:",
    paste0("  - Population control: ", pop_line),
    paste0("  - Regional GDP forced to sum to the national SSP level ",
           "(2024 on): ", if (isTRUE(d$force_gdp_sum)) "yes" else "no"),
    paste0("  - Scenarios: ", paste(config$run$scenarios, collapse = ", "),
           "; GDP models: ", paste(config$run$gdp_models, collapse = ", ")),
    "",
    "Input data versions (data/manifest.yml):",
    versions,
    paste0("  - SSP national data: release 3.1 snapshots (",
           config$inputs$ssp_snap_proj, ", ", config$inputs$ssp_snap_hist,
           ")"),
    "",
    "Files (md5):",
    file_lines,
    "",
    "Written automatically by the pipeline (write_output_readme); do not",
    "edit by hand."
  )
  out <- file.path(config$paths$output, "README.txt")
  writeLines(lines, out)
  invisible(out)
}
