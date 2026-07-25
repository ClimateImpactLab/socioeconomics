"""Tests for irpanel.cohorts. The full build runs once on the shared R cache
(skipped when cache or sources are absent); the step-function shares (the R
catch: cohorts step, population interpolates linearly) and the cohort-sum
identity get focused tests."""

import numpy as np
import pandas as pd
import pytest

from conftest import skip_unless_exists
from irpanel import cohorts, population
from irpanel.compare import pct_diff_stats


@pytest.fixture(scope="module")
def built(config):
    skip_unless_exists(config["paths"]["cache"] / "ir_pop_ghs.csv",
                       "aggregation cache")
    skip_unless_exists(
        config["paths"]["source"] / config["inputs"]["ssp_snap_proj"],
        "SSP snapshot")
    return cohorts.build_cohorts(config, "SSP3")


@pytest.fixture(scope="module")
def built_pop(config):
    skip_unless_exists(config["paths"]["cache"] / "ir_pop_ghs.csv",
                       "aggregation cache")
    return population.build_population(config, "SSP3")


def test_columns_and_range(built):
    assert list(built.columns) == ["hierid", "iso3", "year", "scenario",
                                   "pop0to4", "pop5to64", "pop65plus"]
    assert built["year"].min() == 1981
    assert built["year"].max() == 2100
    for col in ("pop0to4", "pop5to64", "pop65plus"):
        assert (built[col] >= 0).all()


def test_step_function_shares(built, built_pop):
    """Age shares hold constant between 5-year knots while population moves
    annually: within 2020-2024 the share is flat, and the population is not."""
    m = built.merge(built_pop, on=["hierid", "iso3", "year", "scenario"])
    one = m[(m["hierid"] == m["hierid"].iloc[0])
            & m["year"].between(2020, 2029)].sort_values("year")
    share = (one["pop0to4"] / one["pop"]).round(12)
    # Two knots (2020, 2025) -> exactly two distinct share values.
    assert share.nunique() == 2
    assert share.iloc[0] == share.iloc[4]  # 2020..2024 flat
    assert share.iloc[5] == share.iloc[9]  # 2025..2029 flat
    # Population itself interpolates annually.
    assert one["pop"].round(6).nunique() == len(one)


def test_cohorts_sum_to_population(built, built_pop):
    """The three cohorts sum to the IR population (shares sum to ~1)."""
    m = built.merge(built_pop, on=["hierid", "iso3", "year", "scenario"])
    m = m[m["pop"] > 0]
    csum = m["pop0to4"] + m["pop5to64"] + m["pop65plus"]
    assert (np.abs(csum / m["pop"] - 1)).max() < 0.01


def test_against_reference(built, config):
    """Cohort columns match the reference panel at the level the R build
    reaches: median ~0, mean 0.105% (verified identical to R; the residual is
    population's, shared, since the shares match the reference exactly)."""
    ref_path = config["paths"]["reference"] / config["inputs"]["reference"]
    skip_unless_exists(ref_path, "reference panel")
    ref = pd.read_csv(
        ref_path,
        usecols=["hierid", "year", "pop0to4", "pop5to64", "pop65plus"])
    for col in ("pop0to4", "pop5to64", "pop65plus"):
        stats = pct_diff_stats(built, ref, ["hierid", "year"], col)
        assert stats["n_result_only"] == 0
        assert stats["n_reference_only"] == 0
        assert stats["median_abs_pct"] < 1e-6
        assert stats["mean_abs_pct"] < 0.15
