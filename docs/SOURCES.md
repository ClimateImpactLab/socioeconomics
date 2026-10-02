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

Gridded subnational GDP per capita and a matching population raster. The GDP
data comes from the **revised 1990-2022 release, Zenodo record 16741980**.

We use this record rather than the earlier 13943886 because the reference panel
was built from it. Both records cover 1990-2022 (33 annual bands) with the same
national totals, but their subnational downscaling differs; using record 13943886
left the impact-region income ~18% off the reference, and record 16741980
reproduces it (for example a sub-cell region whose 2010 value is 8,742 in this
release and 58,931 in the earlier one, matching the reference exactly). Files
taken from the record: `rast_adm2_gdp_perCapita_1990_2022.tif` and
`tabulated_adm0_gdp_perCapita.csv`.

The 5-arcmin population raster `r_pop_GHS_1990_2022_5arcmin.tif` is not a separate
download. It is inside Kummu's `code_input_data.zip` at
`code_input_data/data_gis/r_pop_GHS_1990_2022_5arcmin.tif`, already on Kummu's
grid. It is GHS-POP R2023A (JRC), the same product across both releases, so it is
retained from record 13943886. `get_data.R` downloads the zip and extracts that
one file. It has 33 bands (1990-2022) and aligns with the GDP raster.

- Zenodo record: https://zenodo.org/records/16741980
- Code: https://github.com/mattikummu/griddedGDPpc
- GDP raster: https://zenodo.org/records/16741980/files/rast_adm2_gdp_perCapita_1990_2022.tif?download=1
- ADM0 table: https://zenodo.org/records/16741980/files/tabulated_adm0_gdp_perCapita.csv?download=1
- Input zip (has the GHS-POP raster): https://zenodo.org/records/13943886/files/code_input_data.zip?download=1
- GHS-POP R2023A (JRC): https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php

## IIASA SSP basic drivers (release 3.1)

National GDP, population, and age cohorts from the SSP basic drivers, release
3.1 (July 2024). This is the release the pipeline uses. Release 3.0 (January
2024) shipped the IIASA GDP 2023 projections from the first review version by
mistake, and release 3.1 corrected them to the second review version. (Release
3.0.1, March 2024, only added historical population reference data and fixed
unicode characters in some country names.)

The 3.1 data was obtained by exporting it manually from the SSP Scenario
Explorer (the direct Downloads page does not list this export, so it is exported
through the explorer). The exported snapshot CSVs are kept in the Box folder
below.

TODO: verify the 3.1 data can be downloaded directly from the official SSP
explorer (the release 3.1 full file) and reproduce from that instead of the Box
snapshots.

TODO: the Box folder is private; make it public so the snapshots are accessible
without special permissions, and keep this link once it is public.

- Release notes: https://data.ece.iiasa.ac.at/ssp/#/about
- Box snapshots: https://uchicago.app.box.com/folder/370257208440?s=fj67ryjmhfg22lgfx16qc9sska2a84v1

## IIASA-WiC historical population and age cohorts

Historical population and age cohorts (IIASA-WiC POP, "Historical Reference"),
used to supply the pre-2020 history the projections do not cover. This currently
comes from a snapshot CSV kept in the same Box folder.

TODO: verify this input can be downloaded manually from the official SSP source.

- Box snapshot: https://uchicago.app.box.com/folder/370257208440?s=fj67ryjmhfg22lgfx16qc9sska2a84v1

## UN WPP 2024

World Population Prospects 2024, demographic indicators, medium variant, from the
UN Population Division. Downloaded June 2026 and checked by md5. Saved as
`WPP2024_GEN_F01_DEMOGRAPHIC_INDICATORS_COMPACT.xlsx`. With `pop_control:
UN_WPP` these totals control national population through the handoff year
(`deltas.pop_handoff_year`); after it the SSP scenario trajectory takes over,
rebased to the WPP level at the handoff so there is no jump at the seam. The
rebasing method (multiplicative, WPP(H) x SSP(t) / SSP(H)) is an open point for
the team. The default handoff is 2023 rather than the 2020 in the team's
decisions doc: WPP observed estimates run through 2023, and income is likewise
observed (PWT-anchored) through 2023, so income and population hand off to SSP
projections in the same year, 2024. Countries without SSP data stay on the WPP
medium variant. This hybrid is new to the new-socioeconomics track — the
legacy pipeline used SSP totals in every year and never scaled population to
UN data.

- Downloads: https://population.un.org/wpp/downloads

## Reference outputs

`../ref_data` holds outputs from a previous run, kept apart from the raw inputs
in `../source_data`. `ir_combined_SSP3_IIASA_v4.csv` there is the per-IR panel
the pipeline reproduces.

## Additional files on the RCC

The IR shapefile and the benchmark panel are read from these paths (see
the track configs under `configs/`); they are not stored or versioned in this
repo:

- `/project/cil/gcp/regions/world-combo-201710/agglomerated-world-new.shp`
- `/project/cil/gcp/integration_replication/inputs/econ/raw/integration-econ-bc39.zarr`

TODO: the raw inputs and reference outputs currently sit under a personal home
dir (`../source_data`, `../ref_data`); move them to a shared location under
/project/cil/gcp (or similar) and update the track configs and the docs once
moved.