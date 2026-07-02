# CIL 2.0 — Impact-Region Socioeconomic Panels

A clean, optimized R pipeline that produces **impact-region (IR) socioeconomic
panels** — income (GDP per capita), population, and age cohorts — for CIL 2.0.
It is a fresh rewrite of the `climate_compensation` "book" pipeline (R) and the
Carleton et al. (2022) `legacy` pipeline (Python), with two deliberate changes
("deltas") relative to the book:

1. **Delta #1 — population control:** scale population to **UN WPP** instead of
   IIASA-WiC. Toggle: `deltas.pop_control` in `config.yml` (`UN_WPP` | `IIASA`).
2. **Delta #2 — GDP sum constraint:** force the **sum of regional GDP to match
   country GDP**. Toggle: `deltas.force_gdp_sum` (`true` | `false`).

Both toggles let us reproduce the book (`IIASA` / `false`) or run CIL 2.0
(`UN_WPP` / `true`).

## Status

**Phase 0 — scaffold only.** Structure, config, and stubs are in place; no
pipeline logic is implemented yet. Every function in `R/` currently
`stop("not implemented")`.

## Layout

```
config.yml     paths, delta toggles, data versions
_targets.R     the DAG (nodes + dependencies)
R/             pipeline modules (io, aggregate_grid, income, population,
               cohorts, postprocess, special_cases, validate, write_outputs, checks)
tests/         testthat placeholders, one per module
data/          manifest + get_data (Phase 1); cache/output/source are gitignored
env/           conda / Docker / Apptainer definitions
docs/          SOURCES + data dictionary
viewer/        panel viewer (later phase)
```

Raw inputs live in `../source_data` and are **referenced, never copied**.
`ir_shapes` and `benchmark` live on the shared `/project/cil/` volume and are
read by absolute path (read-only, never versioned).

## Phase plan

- **Phase 0 — scaffold** (this commit): repo structure, config, stubs, DAG.
- **Phase 1 — data:** `data/manifest.yml`, `data/get_data.R`, `docs/SOURCES.md`;
  wire up DVC; rewrite `read_ssp()` for the SSP 3.0 full xlsx schema.
- **Phase 2 — logic:** implement aggregation, income, population, cohorts,
  postprocess, special cases, checks.
- **Phase 3 — validate & outputs:** benchmark comparison (zarr), NetCDF/CSV
  writers, viewer.

## How to run (once implemented)

```r
# from the repo root, with the renv library restored:
targets::tar_manifest()      # list nodes
targets::tar_visnetwork()    # inspect the DAG
targets::tar_make()          # build the pipeline
```

Delta behaviour is controlled entirely from `config.yml` — no code edits needed
to switch between "reproduce book" and "CIL 2.0".

## Conventions

- Development happens on the `dev` branch; `main` stays clean until a run is
  confirmed. Pushing is done by the maintainer only.
