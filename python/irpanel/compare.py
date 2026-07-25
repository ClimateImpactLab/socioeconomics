"""Validation helpers: compare a built table against a trusted reference.

Every module validates the same way the R side did: join on key columns,
take the percent difference of a value column, and summarize. The bar for a
reproduced column is a median absolute percent difference of about zero.
"""

import numpy as np
import pandas as pd


def pct_diff_stats(result, reference, keys, value, ref_value=None,
                   threshold=1.0):
    """Compare one value column between a result and a reference table.

    :param result: DataFrame with the built values.
    :param reference: DataFrame with the trusted values.
    :param keys: list of join key column names.
    :param value: value column name in result.
    :param ref_value: value column name in reference; defaults to value.
    :param threshold: percent difference over which a row counts as off.
    :return: dict with n_matched, n_result_only, n_reference_only,
        median_abs_pct, mean_abs_pct, max_abs_pct, n_over_threshold.
    """
    ref_value = ref_value or value
    merged = result[keys + [value]].merge(
        reference[keys + [ref_value]].rename(columns={ref_value: "_ref"}),
        on=keys, how="outer", indicator=True,
    )
    both = merged[merged["_merge"] == "both"]
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.abs(both[value] - both["_ref"]) / np.abs(both["_ref"]) * 100
    pct = pct.replace(np.inf, np.nan)
    return {
        "n_matched": len(both),
        "n_result_only": int((merged["_merge"] == "left_only").sum()),
        "n_reference_only": int((merged["_merge"] == "right_only").sum()),
        "median_abs_pct": float(np.nanmedian(pct)) if len(both) else np.nan,
        "mean_abs_pct": float(np.nanmean(pct)) if len(both) else np.nan,
        "max_abs_pct": float(np.nanmax(pct)) if len(both) else np.nan,
        "n_over_threshold": int((pct > threshold).sum()),
    }


def report(stats, label):
    """Format one pct_diff_stats result as a single readable line."""
    return (
        f"{label}: matched {stats['n_matched']:,} "
        f"(result-only {stats['n_result_only']}, "
        f"reference-only {stats['n_reference_only']}), "
        f"median |%diff| {stats['median_abs_pct']:.4g}, "
        f"mean {stats['mean_abs_pct']:.4g}, max {stats['max_abs_pct']:.4g}, "
        f"over threshold {stats['n_over_threshold']}"
    )
