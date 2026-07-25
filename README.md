# Socioeconomic panels

This pipeline builds a per-impact-region socioeconomic panel: income (GDP per
capita), population, and age cohorts for the 24,378 impact regions, covering
1981 to 2100. It reproduces the panel from the Climate Compensation project,
matching `ir_combined_SSP3_IIASA_v4`. The panel is assembled by a chain of R
modules orchestrated by `targets`.

## What it produces

One CSV per scenario and GDP model, `ir_combined_<scenario>_<model>.csv`,
written under `data/output`. Each row is one impact region and year, with these
columns: hierid, iso3, year, gdppc, gdppc_raw, gdppc_raw0, gdp, pop, area_km2,
pop_density, pop_wtd_density, pop0to4, pop5to64, pop65plus. Definitions are in
`docs/data_dictionary.yml`.

## Inputs

Raw inputs are referenced in place, not copied into the repo. `config.yml`
points at a source directory (`../source_data` by default), `data/manifest.yml`
records each file with its checksum, and `Rscript data/get_data.R` fetches or
verifies them. `docs/SOURCES.md` has the full details.

TODO: the raw inputs and reference outputs currently sit under a personal home
dir; move them to a shared location under /project/cil/gcp (or similar) and
update config.yml and the docs once moved.

- Penn World Table 11.0: national GDP per capita, the historical income level
  for the Kummu calibration. https://www.rug.nl/ggdc/productivity/pwt/ (DOI
  https://doi.org/10.34894/FABVLR).
- IIASA SSP basic drivers, release 3.1: national GDP growth (2024-2100),
  population, and age cohorts (2020-2100), plus IIASA-WiC Historical Reference
  population and cohorts for the pre-2020 years. This data currently comes from
  snapshot CSV exports from the SSP Scenario Explorer; the snapshots correspond
  to release 3.1 of the SSP basic drivers and are shared in this Box folder:
  https://uchicago.app.box.com/folder/370257208440?s=fj67ryjmhfg22lgfx16qc9sska2a84v1
  The same data can also be downloaded directly from the official SSP Scenario
  Explorer at https://data.ece.iiasa.ac.at/ssp. TODO: verify the release 3.1
  full file can be downloaded directly from the official explorer and reproduce
  from that instead of the Box snapshots. TODO: the Box folder is private; make
  it public so the snapshots are accessible without special permissions.
- Kummu et al. (2025), Zenodo record 16741980: gridded GDP per capita
  (1990-2022), used to downscale income to regions.
  https://zenodo.org/records/16741980
- GHS-POP R2023A: gridded population (1990-2022), used for the regional
  population distribution.
  https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php
- UN WPP 2024: national population totals, used only when `pop_control` is set
  to UN_WPP. https://population.un.org/wpp/downloads
- Impact-region shapefile: the region boundaries, read from the shared data
  volume. The path is set in `config.yml`; the file is not downloaded.

## Build

All commands run from the project root.

1. Conda environment. `env/environment.yml` is the human-readable spec;
   `env/environment-lock.yml` is the pinned, authoritative version the
   containers build from.

   ```sh
   conda env create -f env/environment.yml
   ```

2. Apptainer image (on the cluster). Load the module first, then build with
   fakeroot:

   ```sh
   module load apptainer
   apptainer build --fakeroot irpanel.sif env/apptainer.def
   ```

3. Docker image (for use outside the cluster):

   ```sh
   docker build -f env/Dockerfile -t irpanel .
   ```

## Run

The pipeline runs `targets::tar_make(callr_function = NULL)`, which builds
io -> aggregate_kummu_to_ir -> build_income -> build_population ->
build_cohorts -> postprocess_panel and writes the panel to `data/output`. Run
`Rscript data/get_data.R` first to fetch or verify the raw inputs.

Directly with the conda environment (`<conda-env-prefix>` is the environment's
install location):

```sh
<conda-env-prefix>/bin/Rscript -e 'targets::tar_make(callr_function = NULL)'
```

Inside the Apptainer container. Bind the data volume so the container sees the
inputs; `<data_root>` is the shared volume that holds the source data and the
impact-region shapefile:

```sh
apptainer exec --bind <data_root> irpanel.sif \
  Rscript -e 'targets::tar_make(callr_function = NULL)'
```

Three notes for running on the cluster:

- Run on a compute node, not the login node. The panel step is heavy enough to
  be killed on the login node (see Memory below).
- Use `tar_make(callr_function = NULL)`. This keeps `targets` in one process
  instead of spawning a worker, which the compute nodes do not allow.
- Call the environment's `Rscript` by its absolute path
  (`<conda-env-prefix>/bin/Rscript`). A `module load` puts the system R (4.3.1)
  ahead on `PATH`, and that build does not have the pipeline's libraries.
  Inside the container this is not a concern; its own `Rscript` is already the
  right one.

## Memory

The panel node is the heavy step. Its peak resident memory is about 8.2 GB
(measured with `/usr/bin/time -v`, max resident set size 8,159,212 kB, wall
time 4:10), running inside the Apptainer container on the cluster. The panel
node dominates because it loads the 618 MB impact-region shapefile and
validates its geometry, which expands to several GB in memory.

Run it on a compute node with at least 12 GB of memory. Eight GB is below the
observed peak and risks an out-of-memory kill.

To re-measure:

```sh
/usr/bin/time -v \
  apptainer exec --bind <data_root> irpanel.sif \
  Rscript -e 'targets::tar_make(callr_function = NULL)'
```

## Configurable choices

Set in `config.yml`, no code changes needed:

- `run.scenario` / `run.gdp_model`: the SSP scenario and GDP model to build.
- `deltas.pop_control`: scale population to `IIASA` (SSP) or `UN_WPP` totals.
  Only `IIASA` is implemented.
- `deltas.force_gdp_sum`: require regional GDP to sum to national GDP. Off; the
  constraint is a marked hook, not yet implemented.

## Status

The panel-building chain is implemented and reproduces the Climate Compensation
project panel: io -> aggregate_kummu_to_ir -> build_income -> build_population
-> build_cohorts -> postprocess_panel. Later stages are stubs: `checks` (panel
contracts), `write_outputs` (NetCDF/CSV writers), and
`validate_against_benchmark`.

## Layout

```
config.yml     paths, run settings, data versions
_targets.R     the pipeline graph (steps and dependencies)
R/             modules: io, aggregate_grid, income, population, cohorts,
               postprocess; stubs: checks, write_outputs, validate
tests/         one test file per module
python/        Python implementation in progress (irpanel package + tests);
               validates against the same reference, writes to data/output/py
data/          manifest, get_data, benchmark_to_csv
env/           conda spec, lock file, Dockerfile, Apptainer definition
docs/          data sources and data dictionary
viewer/        panel viewer
```

Raw inputs live under the source directory in `config.yml` and are referenced,
not copied. The region shapefile and the reference panel are read from the
shared data volume by the paths set in `config.yml`.

## Conventions

Work happens on the `dev` branch; `main` stays clean until a run is confirmed.
