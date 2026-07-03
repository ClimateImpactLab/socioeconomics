# Data sources

Provenance for the raw inputs. Checksums and fetch details live in
`data/manifest.yml`; this file records what each source is and the decisions
behind it. All raw files sit in `../source_data`, outside the repo.

## Penn World Table 11.0

National GDP, population, and PPP conversion factors; the pipeline uses it as
the national income level (rgdpe / pop). Published by the GGDC at the University
of Groningen, DOI 10.34894/FABVLR, on Dataverse (dataverse.nl). Downloaded June
2026 (TODO: confirm exact date). Dataverse has no stable single-file URL for the
workbook, so `get_data.R` pulls the dataset bundle and extracts `pwt110.xlsx`,
verified by md5.

## Kummu et al. (2025)

Gridded subnational GDP per capita and the aligned population raster, from Zenodo
record 13943886. Downloaded June 2026 (TODO: confirm exact date).

We deliberately use the **1990-2022** release, which matches the book pipeline. A
newer record extends the series to 2024; it is intentionally not used here so the
rewrite stays comparable to the book. Files taken directly from the record:
`rast_adm2_gdp_perCapita_1990_2022.tif` and `tabulated_adm0_gdp_perCapita.csv`.

The 5-arcmin population raster `r_pop_GHS_1990_2022_5arcmin.tif` is **not** a
standalone download. It ships inside Kummu's `code_input_data.zip` at
`code_input_data/data_gis/r_pop_GHS_1990_2022_5arcmin.tif`, already resampled to
Kummu's grid. The underlying product is GHS-POP R2023A (JRC), but the aligned
file comes from Kummu's bundle, so we take it from there rather than from a JRC
download. `get_data.R` fetches the zip and extracts that one member.

## IIASA SSP release 3.0

Scenario database, release 3.0 ("basic drivers full", January 2024), from the
IIASA SSP Scenario Explorer (https://data.ece.iiasa.ac.at/ssp). It supplies the
three models the pipeline needs: OECD ENV-Growth 2023, IIASA GDP 2023, and
IIASA-WiC POP 2023. Downloaded manually through the app in June 2026 (TODO:
confirm exact date); there is no stable single-file URL, so this input is
verified but never auto-fetched. Saved as
`1706548837040-ssp_basic_drivers_release_3.0_full.xlsx`.

This is the release-3.0 full workbook, whose sheet layout differs from the two
CSV snapshots the book consumed; the SSP reader is being rewritten for it.

## UN WPP 2024

World Population Prospects 2024, demographic indicators, medium variant, from the
UN Population Division (https://population.un.org/wpp/downloads, Standard
Projections). Downloaded manually in June 2026 (TODO: confirm exact date); no
stable single-file URL, so verified but not auto-fetched. Saved as
`WPP2024_GEN_F01_DEMOGRAPHIC_INDICATORS_COMPACT.xlsx`. Under Delta #1 this
replaces IIASA-WiC as the population control total.

## Not stored here

The IR shapefile (`agglomerated-world-new.shp`) and the benchmark panel
(`integration-econ-bc39.zarr`) are read read-only from the shared `/project/cil/`
volume by absolute path (see `config.yml`). They are neither downloaded nor
versioned in this repo, so they do not appear in `data/manifest.yml`.
