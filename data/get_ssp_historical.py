# Download the IIASA-WiC historical population and age cohorts with pyam and
# write long and wide CSVs into the source dir. The long file is the one
# recorded in data/manifest.yml.

import os

import pyam
import pandas as pd

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "source_data")

hist_pop_all = pyam.read_iiasa(
    "ssp",
    model="IIASA-WiC POP 2025",
    scenario="Historical Reference",
    variable="Population*",
)

# Keep total, sex totals, and sex-by-age; drop education splits
# (education splits have 3 pipes, e.g. Population|Female|Age 20-24|No Education).
selected_variables = [v for v in hist_pop_all.variable if v.count("|") <= 2]
hist_pop = hist_pop_all.filter(variable=selected_variables)

hist_pop_long = hist_pop.data.copy()
hist_pop_wide = hist_pop.timeseries().reset_index()

hist_pop_long.to_csv(
    os.path.join(OUT_DIR, "historical_population_long.csv"), index=False
)
hist_pop_wide.to_csv(
    os.path.join(OUT_DIR, "historical_population_wide.csv"), index=False
)
