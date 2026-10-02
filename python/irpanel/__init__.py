"""Impact-region socioeconomic panel pipeline, Python implementation.

Mirrors the R modules stage for stage: io, aggregate, income, population,
cohorts, postprocess. Both implementations read the same track config
(configs/, selected by IRPANEL_CONFIG) and the same cache CSVs, and both
reproduce the Climate Compensation project panel.
"""

__version__ = "0.1.0"
