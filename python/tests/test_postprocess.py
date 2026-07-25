"""Tests for irpanel.postprocess. The kernel and column rules get synthetic
focused tests; the full panel build needs the IR shapefile and runs only where
it is reachable (the cluster), validating all 14 columns against the
reference."""

import numpy as np
import pandas as pd
import pytest

from conftest import skip_unless_exists
from irpanel import postprocess
from irpanel.compare import pct_diff_stats


@pytest.fixture(scope="module")
def built(config):
    skip_unless_exists(config["paths"]["cache"] / "ir_gdppc_kummu.csv",
                       "aggregation cache")
    skip_unless_exists(
        config["paths"]["source"] / config["inputs"]["ssp_snap_proj"],
        "SSP snapshot")
    skip_unless_exists(config["paths"]["ir_shapes"], "IR shapefile")
    return postprocess.postprocess_panel(config, "SSP3", "IIASA")


def test_bartlett_kernel_hand_check():
    """Weights 13..1 over the trailing window, the oldest value weighted
    highest; truncated and renormalised at the start."""
    out = postprocess.bartlett_smooth(np.array([10.0, 20.0, 40.0]))
    # i=0: only itself. i=1: (10*13 + 20*12) / 25. i=2: weights 13,12,11.
    assert np.allclose(out, [10.0, 370 / 25, 810 / 36])

    # The backward orientation: a spike in the newest year gets the SMALLEST
    # weight (1/91 of a full window), not 13/91.
    x = np.zeros(13)
    x[-1] = 100.0
    out = postprocess.bartlett_smooth(x)
    assert np.isclose(out[-1], 100.0 / 91.0)


def test_bartlett_kernel_missing_values():
    """Missing values are skipped with the weights renormalised; an
    all-missing window is NaN. 2-D input smooths each row independently."""
    out = postprocess.bartlett_smooth(np.array([np.nan, 10.0]))
    assert np.isnan(out[0])
    assert out[1] == 10.0  # only the current value is valid
    two = postprocess.bartlett_smooth(
        np.array([[1.0, 1.0, 1.0], [np.nan, np.nan, np.nan]]))
    assert np.allclose(two[0], 1.0)
    assert np.isnan(two[1]).all()


def test_panel_columns(built):
    assert list(built.columns) == postprocess.PANEL_COLS
    assert built["year"].min() == 1981
    assert built["year"].max() == 2100
    assert built["hierid"].nunique() * 120 == len(built)


def test_income_imputation(built):
    """gdppc is flat over 1981-2015 at the IR's 1990-2015 gdppc_raw mean
    (zero where the mean has no data)."""
    one = built[built["hierid"] == "ABW"].sort_values("year")
    m = one.loc[one["year"].between(1990, 2015), "gdppc_raw"].mean()
    early = one.loc[one["year"] <= 2015, "gdppc"]
    assert np.allclose(early, m)
    # 2016 on is smoothed, so it departs from the flat imputed level.
    assert not np.isclose(one.loc[one["year"] == 2030, "gdppc"].iloc[0], m)


def test_gdppc_column_rules(built):
    """The three gdppc columns: raw is NaN pre-1990 and keeps NaN after; raw0
    zero-fills from 1990 only; gdppc is never NaN."""
    pre = built[built["year"] < 1990]
    assert pre["gdppc_raw"].isna().all()
    assert pre["gdppc_raw0"].isna().all()
    post = built[built["year"] >= 1990]
    filled = post["gdppc_raw"].fillna(0)
    assert np.allclose(post["gdppc_raw0"], filled)
    assert built["gdppc"].notna().all()
    assert (built["gdp"] == built["gdppc"] * built["pop"]).all()


def test_uninhabited_zero(built):
    """23 IRs carry no income in any year and end up gdppc == 0 throughout
    (matching the reference); their gdp is therefore zero too."""
    allzero = built.groupby("hierid")["gdppc"].max() == 0
    assert int(allzero.sum()) == 23
    zero_ids = allzero[allzero].index
    sub = built[built["hierid"].isin(zero_ids)]
    assert (sub["gdp"] == 0).all()


def test_against_reference(built, config):
    """Every panel column matches the reference at the level the R build
    reaches: median ~0 everywhere; the mean residuals are the known shared
    ones (income fallbacks, the reference's Canada share handling)."""
    ref_path = config["paths"]["reference"] / config["inputs"]["reference"]
    skip_unless_exists(ref_path, "reference panel")
    ref = pd.read_csv(ref_path)
    # area_km2 and pop_density carry a ~1e-05% algorithmic difference
    # (pyproj spherical geodesic vs the reference's s2 spherical area), so
    # their median bar is looser than the other columns'.
    for col in postprocess.PANEL_COLS[3:]:
        res = built[["hierid", "year", col]].copy()
        res[col] = res[col].fillna(0)
        stats = pct_diff_stats(res, ref, ["hierid", "year"], col)
        median_bar = 1e-4 if col in ("area_km2", "pop_density") else 1e-6
        assert stats["n_result_only"] == 0, col
        assert stats["n_reference_only"] == 0, col
        assert stats["median_abs_pct"] < median_bar, col
        assert stats["mean_abs_pct"] < 0.2, col
