# Socioeconomic panels

Updated socioeconomic data for the Climate Impact Lab's global impacts work:
impact-region panels of income (GDP per capita), population, and age cohorts,
built by downscaling national data to the 24,378 impact regions. The panels
cover 1981 to 2100.

The update replaces the earlier data sources with newer ones and changes how
population and regional GDP are anchored to national totals.

## Data sources

- Penn World Table 11.0: national GDP per capita, used as the historical income
  level for 2010-2023.
- IIASA SSP 3.0: national GDP growth for 2024-2100, and population and age
  cohorts for 2020-2100.
- IIASA-WiC Historical Reference: population and age cohorts for 1981-2019.
- Kummu et al. (2025): gridded GDP per capita (1990-2022), used to downscale
  income to regions.
- GHS-POP R2023A: gridded population (1990-2022), used for the regional
  population distribution.
- UN WPP 2024: national population totals.

See `docs/SOURCES.md` for details and links.

## Two configurable choices

Set in `config.yml`, no code changes needed:

1. `pop_control`: scale population to UN WPP or to IIASA-WiC national totals.
2. `force_gdp_sum`: require regional GDP to sum to national GDP, or not.

## Status

The structure, config, and data setup are in place. The pipeline functions in
`R/` are not written yet; they are added one at a time.

## Layout

```
config.yml     paths, options, data versions
_targets.R     the pipeline graph (steps and dependencies)
R/             modules: io, aggregate_grid, income, population, cohorts,
               postprocess, special_cases, validate, write_outputs, checks
tests/         one test file per module
data/          manifest, get_data, get_ssp_historical
env/           conda / Docker / Apptainer definitions
docs/          data sources and data dictionary
viewer/        panel viewer
```

Raw inputs live in `../source_data` and are referenced, not copied. The region
shapefile and the reference panel are read by absolute path (see `config.yml`).
TODO: upload these to a shared folder and link them here.

## How to run

```r
# from the repo root, with the renv library restored:
targets::tar_manifest()      # list the steps
targets::tar_make()          # build the panels
```

`Rscript data/get_data.R` downloads or verifies the raw inputs first.

## Conventions

Work happens on the `dev` branch; `main` stays clean until a run is confirmed.