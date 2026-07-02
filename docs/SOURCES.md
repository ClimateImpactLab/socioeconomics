# Data Sources — PLACEHOLDER (Phase 1)

Human-readable companion to `data/manifest.yml`. Will document every raw input:
provider, version / release, download location, base year / units, license, and
any manual preprocessing. Populated in Phase 1.

Planned entries:

- **PWT 11.0** — Penn World Table national accounts (`pwt110.xlsx`).
- **SSP release 3.0 (full)** — IIASA SSP driver database
  (`1706548837040-ssp_basic_drivers_release_3.0_full.xlsx`). NOTE: 3.0 xlsx
  schema differs from the book's CSV snapshots; see `read_ssp()` TODO.
- **UN WPP 2024** — demographic indicators
  (`WPP2024_GEN_F01_DEMOGRAPHIC_INDICATORS_COMPACT.xlsx`); Delta #1 control.
- **Kummu et al. (2025)** — gridded GDP-pc raster, GHS-POP raster, ADM0 table.
- **IR shapes** — `agglomerated-world-new.shp` (shared volume, absolute path).
- **Benchmark** — `integration-econ-bc39.zarr` (shared volume, absolute path).
