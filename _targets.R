# Declarative DAG for the CIL 2.0 IR socioeconomic panel pipeline. Dependencies
# are expressed by target references, not file paths. Inspect with
# tar_manifest() / tar_visnetwork(); build with tar_make().

library(targets)

# Sources every module in R/.
tar_source("R")

tar_option_set(
  packages = c("terra", "sf", "exactextractr", "data.table", "yaml", "ncdf4"),
  format   = "rds"
)

list(
  # Configuration.
  tar_target(config_file, "config.yml", format = "file"),
  tar_target(config,      yaml::read_yaml(config_file)),

  # Raw inputs. ir_shapes and benchmark are read-only absolute paths.
  tar_target(pwt,       read_pwt(config)),
  tar_target(ssp,       read_ssp(config)),
  tar_target(wpp,       read_wpp(config)),
  tar_target(kummu,     read_kummu(config)),
  tar_target(ir_shapes, read_ir_shapes(config)),
  tar_target(benchmark, read_benchmark(config)),

  # Expensive spatial aggregation, cached by targets.
  tar_target(ir_grid, aggregate_kummu_to_ir(kummu, ir_shapes, config)),

  # Income, with special cases applied as explicit downstream nodes so each
  # correction is visible in the DAG.
  tar_target(income_base, build_income(ir_grid, pwt, ssp, config)),
  tar_target(income_ven,  venezuela_fix(income_base, pwt, ssp, config)),
  tar_target(income_cov,  coverage_fallback(income_ven, ssp, config)),
  tar_target(income,      uninhabited_zero(income_cov, ir_grid)),

  # Population and cohorts.
  tar_target(population, build_population(ir_grid, wpp, ssp, config)),
  tar_target(cohorts,    build_cohorts(population, ssp, config)),

  # Final panel.
  tar_target(
    panel,
    postprocess_panel(income, population, cohorts, ir_shapes, config)
  ),

  # Contracts gate the writers; validation is diagnostic only.
  tar_target(checks,     check_panel(panel, config)),
  tar_target(validation, validate_against_benchmark(panel, benchmark, config)),

  # Outputs.
  tar_target(nc_output,  write_netcdf(panel, config, checks)),
  tar_target(csv_output, write_csv_mirror(panel, config, checks))
)
