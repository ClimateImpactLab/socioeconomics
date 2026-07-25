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
- IIASA SSP basic drivers, release 3.1: national GDP growth (2024-2100) and
  population and age cohorts (2020-2100), currently from Box snapshot CSVs.
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
data/          manifest, get_data, benchmark_to_csv
env/           conda / Docker / Apptainer definitions
docs/          data sources and data dictionary
viewer/        panel viewer
```

Raw inputs live in `../source_data` and are referenced, not copied. The region
shapefile and the reference panel are read by absolute path (see `config.yml`).

## How to run

```r
targets::tar_manifest()                    # list the steps
targets::tar_make(callr_function = NULL)   # build and write the panel
```

`Rscript data/get_data.R` downloads or verifies the raw inputs first. The
aggregation step writes a cache under `data/cache` that the build steps read.

Three notes for running on the RCC:

- Run on a compute node, not the login node. The panel step is heavy enough to
  be killed on the login node (see Memory below).
- Use `tar_make(callr_function = NULL)`. This keeps `targets` in one process
  instead of spawning a worker, which the compute nodes do not allow.
- Call the environment's `Rscript` by its absolute path, for example
  `/project/cil/home_dirs/rcc/envs/socioeconomics-new/bin/Rscript`. A `module
  load` puts the system R (4.3.1) ahead on `PATH` and that build does not have
  the pipeline's libraries.

The container carries its own R and libraries, so inside it plain `Rscript`
already resolves to the right one (see `env/`).

## Memory

The panel node is the heavy step. Its peak resident memory is about 8.2 GB
(measured with `/usr/bin/time -v`, max resident set size 8,159,212 kB, wall
time 4:10), running inside the Apptainer container on the cluster. The panel
node dominates because it loads the 618 MB IR shapefile and validates its
geometry, which expands to several GB in memory.

Run it on a compute node with at least 12 GB of memory. Eight GB is below the
observed peak and risks an out-of-memory kill.

To re-measure:

```sh
/usr/bin/time -v \
  apptainer exec --bind /project/cil irpanel.sif \
  Rscript -e 'targets::tar_make(callr_function = NULL)'
```

## Conventions

Work happens on the `dev` branch; `main` stays clean until a run is confirmed.
