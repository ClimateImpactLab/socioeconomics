# Pipeline DAG: io -> aggregate -> income -> population -> cohorts ->
# postprocess, then write the panel. The build steps are self-contained (each
# reads the aggregation cache and reproduces its part of the reference panel),
# so they take config rather than upstream tables; they depend on ir_grid only
# for ordering, since ir_grid writes the cache they read. Inspect with
# tar_manifest() / tar_visnetwork(); build with tar_make().

library(targets)

# Sources every module in R/.
tar_source("R")

tar_option_set(
  packages = c("terra", "sf", "exactextractr", "data.table", "yaml", "ncdf4",
               "readxl", "countrycode"),
  format   = "rds"
)

list(
  # Configuration, and the scenario / GDP model the run builds.
  tar_target(config_file, "config.yml", format = "file"),
  tar_target(config,      yaml::read_yaml(config_file)),
  tar_target(scenario,    config$run$scenario),
  tar_target(gdp_model,   config$run$gdp_model),

  # Raw inputs.
  tar_target(kummu,     read_kummu(config)),
  tar_target(ir_shapes, read_ir_shapes(config)),

  # Expensive spatial aggregation. Writes the CSV cache the build steps read;
  # returns TRUE as an ordering marker rather than the large tables.
  tar_target(ir_grid, {
    aggregate_kummu_to_ir(kummu, ir_shapes, config)
    TRUE
  }),

  # Build steps. Each reads the cache and reproduces one part of the panel.
  tar_target(income,     {
    ir_grid
    build_income(config, scenario, gdp_model)
  }),
  tar_target(population, {
    ir_grid
    build_population(config, scenario)
  }),
  tar_target(cohorts,    {
    ir_grid
    build_cohorts(config, scenario)
  }),

  # Final panel. postprocess_panel is self-contained and repeats the income,
  # population, and cohort steps internally.
  tar_target(panel, {
    ir_grid
    postprocess_panel(config, scenario, gdp_model)
  }),

  # Write the panel to the output directory.
  tar_target(panel_file, {
    dir.create(config$paths$output, showWarnings = FALSE, recursive = TRUE)
    out <- file.path(config$paths$output,
                     paste0("ir_combined_", scenario, "_", gdp_model, ".csv"))
    data.table::fwrite(panel, out)
    out
  }, format = "file")
)
