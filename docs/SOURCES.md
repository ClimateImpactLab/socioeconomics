# Data sources

What each raw input is and where it comes from. Checksums and fetch details are
in `data/manifest.yml`. Raw files sit in `../source_data`, outside the repo.

## Penn World Table 11.0

National GDP, population, and PPP conversion factors, used as the national income
level (rgdpe / pop). From the GGDC at the University of Groningen, DOI
10.34894/FABVLR, on Dataverse. Downloaded June 2026. `get_data.R` downloads the
dataset bundle, extracts `pwt110.xlsx`, and checks its md5.

- Homepage: https://www.rug.nl/ggdc/productivity/pwt/
- Dataset (DOI): https://doi.org/10.34894/FABVLR
- Bundle download: https://dataverse.nl/api/access/dataset/:persistentId?persistentId=doi:10.34894/FABVLR

## Kummu et al. (2025)

Gridded subnational GDP per capita and a matching population raster, from Zenodo
record 13943886. Downloaded June 2026.

Uses the 1990-2022 release. Files taken from the record: `rast_adm2_gdp_perCapita_1990_2022.tif`
and `tabulated_adm0_gdp_perCapita.csv`.

The 5-arcmin population raster `r_pop_GHS_1990_2022_5arcmin.tif` is not a separate
download. It is inside Kummu's `code_input_data.zip` at
`code_input_data/data_gis/r_pop_GHS_1990_2022_5arcmin.tif`, already on Kummu's
grid. It is based on GHS-POP R2023A (JRC), but taken from Kummu's zip so the grid
matches. `get_data.R` downloads the zip and extracts that one file.

- Zenodo record: https://zenodo.org/records/13943886
- Code: https://github.com/mattikummu/griddedGDPpc
- GDP raster: https://zenodo.org/records/13943886/files/rast_adm2_gdp_perCapita_1990_2022.tif?download=1
- ADM0 table: https://zenodo.org/records/13943886/files/tabulated_adm0_gdp_perCapita.csv?download=1
- Input zip (has the GHS-POP raster): https://zenodo.org/records/13943886/files/code_input_data.zip?download=1
- GHS-POP R2023A (JRC): https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php

## IIASA SSP release 3.0

SSP scenario database, release 3.0 ("basic drivers full", January 2024), from the
IIASA SSP Scenario Explorer. Has the three models the pipeline uses: OECD
ENV-Growth 2023, IIASA GDP 2023, and IIASA-WiC POP 2023. Downloaded June 2026 and
checked by md5. Saved as
`1706548837040-ssp_basic_drivers_release_3.0_full.xlsx`.

Population and cohorts in this file start at 2020.

- SSP Explorer: https://data.ece.iiasa.ac.at/ssp

## IIASA-WiC historical population and age cohorts

Historical population and age cohorts by sex (Population, Population|Male|Age X-Y,
Population|Female|Age X-Y), scenario "Historical Reference", model IIASA-WiC POP
2025. Covers 1950-2025 in 5-year steps. This is the pre-2020 cohort history that
the release 3.0 file does not have. Saved as
`ssp_wic2025_historical_reference_pop_cohorts.csv`.

Downloaded with `data/get_ssp_historical.py`, which pulls it from the IIASA SSP
database through `pyam` and drops the education splits.

This file is IIASA-WiC POP 2025; the projection cohorts (2020 on) come from
IIASA-WiC POP 2023 in the release 3.0 file. The two are joined at the historical
years.

- SSP database: https://data.ece.iiasa.ac.at/ssp
- pyam docs: https://pyam-iamc.readthedocs.io/

## UN WPP 2024

World Population Prospects 2024, demographic indicators, medium variant, from the
UN Population Division. Downloaded June 2026 and checked by md5. Saved as
`WPP2024_GEN_F01_DEMOGRAPHIC_INDICATORS_COMPACT.xlsx`. This is the population
control total instead of IIASA-WiC.

- Downloads: https://population.un.org/wpp/downloads

## Reference outputs

`../ref_data` holds outputs from a previous run, kept apart from the raw inputs
in `../source_data`. `ir_combined_SSP3_IIASA_v4.csv` there is the per-IR panel
the comparisons in `R/validate.R` check against.

## Additional files on the RCC

The IR shapefile and the benchmark panel are read from these paths (see
`config.yml`); they are not stored or versioned in this repo:

- `/project/cil/gcp/regions/world-combo-201710/agglomerated-world-new.shp`
- `/project/cil/gcp/integration_replication/inputs/econ/raw/integration-econ-bc39.zarr`