"""Impact-region socioeconomic panel pipeline (CIL 2.0), Python implementation.

Mirrors the R modules stage for stage: io, aggregate, income, population,
cohorts, postprocess. Both implementations read the same config.yml and the
same cache CSVs, and both reproduce the Climate Compensation project panel.
"""

__version__ = "0.1.0"
