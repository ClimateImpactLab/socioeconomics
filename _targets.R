# Pipeline DAG: io -> aggregate -> income -> population -> cohorts ->
# postprocess, then write one panel per scenario x GDP-model combination
# (run$scenarios x run$gdp_models in the track config). The build steps
# are self-contained (each reads the
# aggregation cache and rebuilds its part), so they take config rather than
# upstream tables; they depend on ir_grid only for ordering, since ir_grid
# writes the cache they read. The IR area is computed once and shared by all
# panels, so the shapefile is read once per tar_make. For a quick
# single-combination run, name the target:
# tar_make(names = "panel_file_SSP3_IIASA"). Inspect with tar_manifest() /
# tar_visnetwork().
#
# Tracks: one config per track under configs/, one store per track under
# stores/ (_targets.yaml). TAR_PROJECT selects both, e.g.
# TAR_PROJECT=new-socioeconomics; the default is the book reproduction
# (climate-compensation). IRPANEL_CONFIG overrides the config path.

library(targets)

# Sources every module in R/.
tar_source("R")

tar_option_set(
  packages = c("terra", "sf", "exactextractr", "data.table", "yaml", "ncdf4",
               "readxl", "countrycode"),
  format   = "rds"
)

# Track selection: TAR_PROJECT picks configs/<project>.yml to match the store
# it selects in _targets.yaml; IRPANEL_CONFIG overrides the config path. Both
# set and disagreeing is a configuration error, not a choice to make here.
track <- Sys.getenv("TAR_PROJECT", "main")
if (track == "main") track <- "climate-compensation"
config_path <- Sys.getenv("IRPANEL_CONFIG")
if (!nzchar(config_path)) {
  config_path <- file.path("configs", paste0(track, ".yml"))
} else if (nzchar(Sys.getenv("TAR_PROJECT")) &&
           basename(config_path) != paste0(track, ".yml")) {
  stop("IRPANEL_CONFIG (", config_path, ") contradicts TAR_PROJECT (",
       Sys.getenv("TAR_PROJECT"), ")")
}

# The combination set, read at DAG-definition time to enumerate targets. A
# versioned track must write into a folder named after its version, so a
# mismatched bump stops here, before any target runs.
cfg_probe <- yaml::read_yaml(config_path)
if (!is.null(cfg_probe$version) &&
    basename(cfg_probe$paths$output) != as.character(cfg_probe$version)) {
  stop("config version ", cfg_probe$version,
       " does not match the output folder ", cfg_probe$paths$output)
}
combos <- expand.grid(
  scen  = cfg_probe$run$scenarios,
  model = cfg_probe$run$gdp_models,
  stringsAsFactors = FALSE
)

shared <- list(
  tar_target_raw("config_file", config_path, format = "file"),
  tar_target(config, yaml::read_yaml(config_file)),

  # Raw inputs.
  tar_target(kummu,     read_kummu(config)),
  tar_target(ir_shapes, read_ir_shapes(config)),

  # Expensive spatial aggregation. Writes the CSV cache the build steps read;
  # returns TRUE as an ordering marker rather than the large tables.
  tar_target(ir_grid, {
    aggregate_kummu_to_ir(kummu, ir_shapes, config)
    TRUE
  }),

  # Geodesic IR area, computed once and shared by every panel.
  tar_target(ir_area, compute_ir_area(config))
)

# Per-scenario targets: population and cohorts do not depend on the GDP model.
per_scenario <- unlist(lapply(unique(combos$scen), function(sc) {
  list(
    tar_target_raw(
      paste0("population_", sc),
      substitute({
        ir_grid
        build_population(config, sc)
      }, list(sc = sc))
    ),
    tar_target_raw(
      paste0("cohorts_", sc),
      substitute({
        ir_grid
        build_cohorts(config, sc)
      }, list(sc = sc))
    )
  )
}), recursive = FALSE)

# Per-combination targets: income, the panel, its checks, and its CSV. The
# CSV depends on the checks, so nothing is written for a panel that failed
# its checks.
per_combo <- unlist(lapply(seq_len(nrow(combos)), function(i) {
  sc  <- combos$scen[i]
  gm  <- combos$model[i]
  tag <- paste0(sc, "_", gm)
  list(
    tar_target_raw(
      paste0("income_", tag),
      substitute({
        ir_grid
        build_income(config, sc, gm)
      }, list(sc = sc, gm = gm))
    ),
    tar_target_raw(
      paste0("panel_", tag),
      substitute({
        ir_grid
        postprocess_panel(config, sc, gm, area = ir_area)
      }, list(sc = sc, gm = gm))
    ),
    tar_target_raw(
      paste0("checks_", tag),
      substitute(
        check_panel(panel, config, sc, gm),
        list(sc = sc, gm = gm, panel = as.symbol(paste0("panel_", tag)))
      )
    ),
    tar_target_raw(
      paste0("panel_file_", tag),
      substitute({
        checks
        dir.create(config$paths$output, showWarnings = FALSE,
                   recursive = TRUE)
        out <- file.path(config$paths$output,
                         paste0("ir_combined_", sc, "_", gm, ".csv"))
        data.table::fwrite(panel, out)
        out
      }, list(sc = sc, gm = gm,
              panel = as.symbol(paste0("panel_", tag)),
              checks = as.symbol(paste0("checks_", tag)))),
      format = "file"
    )
  )
}), recursive = FALSE)

# Cross-panel checks over all combinations, then the main Zarr store,
# gated on them.
tags <- paste0(combos$scen, "_", combos$model)
panel_syms <- lapply(paste0("panel_", tags), as.symbol)
names(panel_syms) <- tags
cross <- tar_target_raw(
  "checks_cross",
  as.call(list(quote(check_cross_panel),
               as.call(c(list(quote(list)), panel_syms)),
               quote(config)))
)

file_syms <- lapply(paste0("panel_file_", tags), as.symbol)
zarr <- tar_target_raw(
  "zarr_store",
  as.call(list(quote(`{`), quote(checks_cross),
               as.call(list(quote(write_zarr), quote(config),
                            as.call(c(list(quote(c)), file_syms)))))),
  format = "file"
)

# README in the output folder saying how the data was made, rewritten
# whenever the panels are.
readme <- tar_target_raw(
  "output_readme",
  as.call(list(quote(write_output_readme), quote(config), config_path,
               as.call(c(list(quote(c)), file_syms)), quote(zarr_store))),
  format = "file"
)

# MetaCSV metadata file next to the panel CSVs, and the self-contained
# NetCDF over all combinations carrying the same metadata.
metadata <- tar_target_raw(
  "output_metadata",
  as.call(list(quote(write_output_metadata), quote(config), config_path,
               as.call(c(list(quote(c)), file_syms)), quote(zarr_store))),
  format = "file"
)

netcdf <- tar_target_raw(
  "netcdf_store",
  as.call(list(quote(write_netcdf), quote(config),
               as.call(c(list(quote(c)), file_syms)),
               quote(output_metadata))),
  format = "file"
)

c(shared, per_scenario, per_combo,
  list(cross, zarr, readme, metadata, netcdf))
