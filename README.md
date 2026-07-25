# Socioeconomic panels

Updated socioeconomic data for the Climate Impact Lab's global impacts work:
impact-region panels of income (GDP per capita), population, and age cohorts,
built by downscaling national data to the 24,378 impact regions. The panels
cover 1981 to 2100.

The panel is assembled by a chain of R modules and written in the shape of the
reference `ir_combined` files.

## Data sources

- Penn World Table 11.0: national GDP per capita, the historical income level
  for the Kummu calibration.
- IIASA SSP: national GDP growth (2024-2100) and population and age cohorts
  (2020-2100). Two sources are selectable (see below): the book's SSP snapshots
  or the release 3.0 xlsx.
- IIASA-WiC Historical Reference: population and age cohorts for 1981-2019.
- Kummu et al. (2025), Zenodo record 16741980: gridded GDP per capita
  (1990-2022), used to downscale income to regions.
- GHS-POP R2023A: gridded population (1990-2022), used for the regional
  population distribution.
- UN WPP 2024: national population totals (used only when `pop_control` is set
  to UN_WPP).

See `docs/SOURCES.md` for details and links.

## Configurable choices

Set in `config.yml`, no code changes needed:

- `run.scenario` / `run.gdp_model`: the SSP scenario and GDP model to build.
- `options.ssp_source`: `snapshots` (the book's SSP snapshot CSVs) or `xlsx`
  (release 3.0 full).
- `deltas.pop_control`: scale population to `IIASA` (SSP) or `UN_WPP` totals.
  Only `IIASA` is implemented.
- `deltas.force_gdp_sum`: require regional GDP to sum to national GDP. Off; the
  constraint is a marked hook, not yet implemented.

## Status

The panel-building chain is implemented and reproduces the reference panel:
io -> aggregate_kummu_to_ir -> build_income -> build_population -> build_cohorts
-> postprocess_panel. Later stages are stubs: `checks` (panel contracts),
`write_outputs` (NetCDF/CSV writers), and `validate_against_benchmark`.

## Layout

```
config.yml     paths, options, run settings, data versions
_targets.R     the pipeline graph (steps and dependencies)
R/             modules: io, aggregate_grid, income, population, cohorts,
               postprocess; stubs: checks, write_outputs, validate
tests/         one test file per module
data/          manifest, get_data, get_ssp_historical, benchmark_to_csv
env/           conda / Docker / Apptainer definitions
docs/          data sources and data dictionary
viewer/        panel viewer
```

Raw inputs live in `../source_data` and are referenced, not copied. The region
shapefile and the reference panel are read by absolute path (see `config.yml`).

## How to run

```r
targets::tar_manifest()      # list the steps
targets::tar_make()          # build and write the panel
```

`Rscript data/get_data.R` downloads or verifies the raw inputs first. The
aggregation step writes a cache under `data/cache` that the build steps read.

## Conventions

Work happens on the `dev` branch; `main` stays clean until a run is confirmed.
