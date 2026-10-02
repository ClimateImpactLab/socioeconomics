# Socioeconomic panels

This pipeline builds a per-impact-region socioeconomic panel: income (GDP per
capita), population, and age cohorts for the 24,378 impact regions, covering
1981 to 2100. The panel is assembled by a chain of R modules orchestrated by
`targets`, in two tracks, each with its own config under `configs/` and its
own store under `stores/`:

- climate-compensation (default): the book reproduction, matching the Climate
  Compensation project's `ir_combined_SSP3_IIASA_v4`.
- new-socioeconomics: the updated panel (UN WPP population control with an
  SSP handoff, regional GDP forced to the national level).

## What it produces

One CSV per scenario and GDP model, `ir_combined_<scenario>_<model>.csv`, plus
a Zarr store and a provenance README.txt, written to the track's output folder
(`paths.output` in the config: `data/output` for climate-compensation,
`/project/cil/gcp/outputs_newsocioeconomics/socioeconomics` for
new-socioeconomics). Each CSV row is one impact region and year, with these
columns: hierid, iso3, year, gdppc, gdppc_raw, gdppc_raw0, gdp, pop, area_km2,
pop_density, pop_wtd_density, pop0to4, pop5to64, pop65plus. Definitions are in
`docs/data_dictionary.yml`.

## Inputs

Raw inputs are referenced in place, not copied into the repo. The track
configs point at a source directory (`../source_data` by default),
`data/manifest.yml` records each file with its checksum, and
`Rscript data/get_data.R` fetches or verifies them. `docs/SOURCES.md` has the
full details.

TODO: the raw inputs and reference outputs currently sit under a personal home
dir; move them to a shared location under /project/cil/gcp (or similar) and
update the configs and the docs once moved.

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
- UN WPP 2024: national population totals through the population handoff year,
  used only when `pop_control` is set to UN_WPP.
  https://population.un.org/wpp/downloads
- Impact-region shapefile: the region boundaries, read from the shared data
  volume. The path is set in the track configs; the file is not downloaded.

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
build_cohorts -> postprocess_panel and writes the panel to the track's output
folder. Run `Rscript data/get_data.R` first to fetch or verify the raw inputs.

The track is selected with the `TAR_PROJECT` environment variable, which picks
both the config (`configs/<track>.yml`) and the store (`stores/<track>`,
mapped in `_targets.yaml`), so the tracks never invalidate each other. Unset,
it runs the book reproduction (climate-compensation). `IRPANEL_CONFIG` can
point at an explicit config file instead; combined with a contradicting
`TAR_PROJECT` it is an error.

Directly with the conda environment (`<conda-env-prefix>` is the environment's
install location):

```sh
# book reproduction (default track)
<conda-env-prefix>/bin/Rscript -e 'targets::tar_make(callr_function = NULL)'

# new-socioeconomics track
TAR_PROJECT=new-socioeconomics \
  <conda-env-prefix>/bin/Rscript -e 'targets::tar_make(callr_function = NULL)'
```

Inside the Apptainer container. Bind the data volume so the container sees the
inputs; `<data_root>` is the shared volume that holds the source data and the
impact-region shapefile:

```sh
# book reproduction (default track)
apptainer exec --bind <data_root> irpanel.sif \
  Rscript -e 'targets::tar_make(callr_function = NULL)'

# new-socioeconomics track
apptainer exec --bind <data_root> --env TAR_PROJECT=new-socioeconomics \
  irpanel.sif Rscript -e 'targets::tar_make(callr_function = NULL)'
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

Set per track in `configs/<track>.yml`, no code changes needed:

- `run.scenario` / `run.gdp_model`: the SSP scenario and GDP model to build.
- `deltas.pop_control`: national population control totals. `IIASA` scales to
  the SSP scenario totals in every year (the book reproduction). `UN_WPP`
  scales to UN WPP 2024 through `deltas.pop_handoff_year`, then follows the
  SSP scenario trajectory rebased to the WPP level at the handoff, so the
  national path is continuous at the seam and scenarios diverge after it.
  Countries the SSP does not cover stay on WPP in every year; countries WPP
  does not cover keep the frozen-GHS fallback. The rebasing method
  (multiplicative, WPP(H) x SSP(t) / SSP(H)) is an open point for the team.
  This hybrid is new to the new-socioeconomics track: the legacy pipeline
  used SSP totals in every year and never scaled population to UN data.
- `deltas.pop_handoff_year`: the last year population follows UN WPP under
  `UN_WPP`. The default is 2023, not the 2020 in the team's decisions doc:
  WPP observed estimates run through 2023, and income is likewise observed
  (PWT-anchored) through 2023, so income and population hand off to SSP
  projections in the same year, 2024.
- `deltas.force_gdp_sum`: rescale regional income so IR GDP sums to the
  national SSP level from 2024 on. On for the new-socioeconomics track, off
  for the book reproduction.

## Status

The panel-building chain is implemented and reproduces the Climate Compensation
project panel: io -> aggregate_kummu_to_ir -> build_income -> build_population
-> build_cohorts -> postprocess_panel -> check_panel (hard contracts that
gate the writers) -> write_zarr (one Zarr store over all scenario x model
combinations, mirroring the benchmark layout). Remaining stub:
`validate_against_benchmark`.

## Layout

```
configs/       one config per track: climate-compensation (book
               reproduction, default), new-socioeconomics
_targets.R     the pipeline graph (steps and dependencies)
_targets.yaml  track -> store mapping (stores/<track>)
R/             modules: io, aggregate_grid, income, population, cohorts,
               postprocess, checks, write_outputs; stub: validate
tests/         one test file per module
python/        Python implementation (irpanel package + tests); validates
               against the same reference, writes to <output>/py and
               data/cache/py; known residual: docs/python-reproduction.md
data/          manifest, get_data, benchmark_to_csv
env/           conda spec, lock file, Dockerfile, Apptainer definition
docs/          data sources, data dictionary, Python reproduction status
viewer/        panel viewer
```

Raw inputs live under the source directory in the track configs and are
referenced, not copied. The region shapefile and the reference panel are read
from the shared data volume by the paths set there.

## Conventions

Work happens on the `dev` branch; `main` stays clean until a run is confirmed.
