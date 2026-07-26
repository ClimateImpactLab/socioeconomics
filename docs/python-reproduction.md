# Python reproduction: status and known residual

The Python implementation (`python/irpanel`) reproduces the R pipeline
end to end: aggregation (exactextract), income, population, cohorts, and
postprocessing. Validation is cache-to-cache against the R outputs and
panel-level against the reference `ir_combined_SSP3_IIASA_v4`.

Python reproduces the R pipeline to float noise across the panel except on
252 impact regions listed in `residual_irs.csv` (this directory, ranked by
reference 2020 population, with each region's worst cache-to-cache
difference). All of them have degenerate geometry in the region shapefile:
zero-area or self-crossing rings in fragmented multi-ring features. The
other 24,126 regions match the R cache at float noise across all four
aggregation CSVs (population max 1e-3 %, GDP per capita max 5e-4 %, over
all years), and the panel medians against the reference are at float noise
for every column on both sides.

Cause: the two implementations clean geometry with different libraries.
Python uses GEOS (`shapely make_valid`), the standard planar path; R's
`sf::st_make_valid` routes geographic coordinates through s2. On valid
geometry the two agree; on the degenerate rings they resolve the invalid
structure differently (GEOS is orientation-agnostic and keeps the fragment
rings additive; s2 resolves them on the sphere, and its outcome further
depends on the s2 snapshot the R package vendors). The reference itself
sits inside this ambiguity: v4 diverges from the R pipeline by up to
~145 % on the same features, so they are a known unstable set under any
library change.

`gdppc` is unaffected after postprocessing (the population-weighted mean
is a ratio, so coverage differences cancel, and smoothing/imputation
absorb the rest: residual-region gdppc vs reference median 0.01 %, mean
0.6 %). `area_km2` is also unaffected (the reference area matches the
GEOS-read geometry). The residual is carried by the direct sums on these
regions only: `pop`, `gdp`, the cohort columns, and the density columns.
Most of it is small — the median residual-region population deviation vs
the reference is 0.7 % — and the largest deviations on inhabited regions
are UKR.4.R8248fcb59da0b28d and UKR.27.R3dabfbf7bd3008ae (~1.4-1.7 M
people, ~21 % vs the reference where R has ~0.7 %) and
JPN.12.Re77fb48f7dbf5221 (~1.3 M, ~20 % vs ~0 %).

The cache-to-cache test (`python/tests/test_aggregate.py`) asserts float
noise for all regions outside the list and that no region outside the
list regresses.

## CIL 2.0 improvement (not part of the reproduction)

TODO: for the CIL 2.0 data, which is not bound to reproduce v4, repair the
degenerate-geometry features once at the source (fix zero-area and
self-crossing rings in the region shapefile, or publish a cleaned copy) so
that every reader — R, Python, any GEOS or s2 version — assembles the same
geometry and the aggregation agrees exactly. This is the proper fix; it
changes the reproduction target, so it belongs to the CIL 2.0 phase.
