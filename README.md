# CIL 2.0 — Impact-Region Socioeconomic Panels

An R pipeline that produces impact-region (IR) socioeconomic panels — income
(GDP per capita), population, and age cohorts — for CIL 2.0.

Two behaviours are controlled from `config.yml`:

1. **Population control** (`deltas.pop_control`): scale population to UN WPP
   (`UN_WPP`) or to IIASA-WiC (`IIASA`).
2. **GDP sum constraint** (`deltas.force_gdp_sum`): force the sum of regional
   GDP to match country GDP (`true`) or leave it unconstrained (`false`).

No code changes are needed to switch either behaviour.

## Status

The repository is scaffolded: structure, config, and the data layer are in
place. The pipeline functions in `R/` are stubs that `stop("not implemented")`;
they are filled in module by module.

## Layout

```
config.yml     paths, delta toggles, data versions
_targets.R     the DAG (nodes + dependencies)
R/             pipeline modules (io, aggregate_grid, income, population,
               cohorts, postprocess, special_cases, validate, write_outputs, checks)
tests/         testthat files, one per module
data/          manifest, get_data, get_ssp_historical; cache/output/source are gitignored
env/           conda / Docker / Apptainer definitions
docs/          SOURCES and data dictionary
viewer/        panel viewer
```

Raw inputs live in `../source_data` and are referenced, never copied.
`ir_shapes` and `benchmark` live on the shared `/project/cil/` volume and are
read by absolute path, read-only.

## How to run

```r
# from the repo root, with the renv library restored:
targets::tar_manifest()      # list nodes
targets::tar_visnetwork()    # inspect the DAG
targets::tar_make()          # build the pipeline
```

## Conventions

- Development happens on the `dev` branch; `main` stays clean until a run is
  confirmed. Pushing is done by the maintainer only.
