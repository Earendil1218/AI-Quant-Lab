"""基准比较和统一样本相关性的确定性测试。Comparison and correlation tests."""

from __future__ import annotations

from math import sqrt

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from research.comparison import (
    calculate_active_returns,
    calculate_annualized_tracking_error,
    calculate_return_correlation,
    compare_cumulative_performance,
)


def return_series(
    dates: list[str],
    values: list[object],
    name: str | None = None,
) -> pd.Series:
    return pd.Series(
        values,
        index=pd.DatetimeIndex(dates, name="date"),
        name=name,
    )


def test_active_returns_are_calculated_after_exact_alignment() -> None:
    asset = return_series(
        ["2026-01-01", "2026-01-02", "2026-01-03"],
        [0.10, 0.05, -0.02],
    )
    benchmark = return_series(
        ["2026-01-01", "2026-01-02", "2026-01-03"],
        [0.04, 0.03, -0.01],
    )

    actual = calculate_active_returns(asset, benchmark, " nvda ", "spy")
    expected = return_series(
        ["2026-01-01", "2026-01-02", "2026-01-03"],
        [0.06, 0.02, -0.01],
        "NVDA_minus_SPY_active_return",
    ).astype("float64")

    assert_series_equal(actual, expected)


def test_partial_overlap_is_not_filled() -> None:
    asset = return_series(
        ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
        [0.01, 0.02, 0.03, 0.04],
    )
    benchmark = return_series(
        ["2026-01-01", "2026-01-02", "2026-01-04"],
        [0.005, 0.01, 0.02],
    )

    actual = calculate_active_returns(asset, benchmark, "ASSET", "BENCH")

    assert actual.index.tolist() == list(
        pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-04"])
    )
    assert actual.tolist() == pytest.approx([0.005, 0.01, 0.02])
    assert not actual.isna().any()


def test_leading_nan_is_removed_before_benchmark_comparison() -> None:
    asset = return_series(
        ["2026-01-01", "2026-01-02", "2026-01-03"],
        [np.nan, 0.10, 0.20],
    )
    benchmark = return_series(
        ["2026-01-02", "2026-01-03", "2026-01-04"],
        [np.nan, 0.05, 0.01],
    )

    actual = calculate_active_returns(asset, benchmark, "A", "B")

    assert actual.index.tolist() == [pd.Timestamp("2026-01-03")]
    assert actual.iloc[0] == pytest.approx(0.15)


def test_no_common_date_is_an_error() -> None:
    asset = return_series(["2026-01-01"], [0.10])
    benchmark = return_series(["2026-01-02"], [0.05])

    with pytest.raises(ValueError, match="no common dates"):
        calculate_active_returns(asset, benchmark, "A", "B")


def test_benchmark_comparison_does_not_mutate_inputs() -> None:
    asset = return_series(["2026-01-01", "2026-01-02"], [0.10, 0.05], "old")
    benchmark = return_series(["2026-01-01", "2026-01-02"], [0.04, 0.03])
    original_asset = asset.copy(deep=True)
    original_benchmark = benchmark.copy(deep=True)

    compare_cumulative_performance(asset, benchmark, "A", "B")

    assert_series_equal(asset, original_asset)
    assert_series_equal(benchmark, original_benchmark)


def test_rejects_identical_normalized_asset_and_benchmark_symbols() -> None:
    returns = return_series(["2026-01-01"], [0.10])

    with pytest.raises(ValueError, match="distinct"):
        calculate_active_returns(returns, returns, "spy", " SPY ")


def test_cumulative_performance_compounds_from_shared_start() -> None:
    asset = return_series(
        ["2026-01-01", "2026-01-02", "2026-01-03"],
        [0.50, 0.10, -0.10],
    )
    benchmark = return_series(
        ["2026-01-02", "2026-01-03"],
        [0.05, 0.00],
    )

    actual = compare_cumulative_performance(asset, benchmark, "nvda", "spy")
    expected = pd.DataFrame(
        {
            "NVDA": [0.10, -0.01],
            "SPY": [0.05, 0.05],
        },
        index=pd.DatetimeIndex(["2026-01-02", "2026-01-03"], name="date"),
    )

    assert_frame_equal(actual, expected)


def test_tracking_error_uses_sample_std_and_annualization() -> None:
    asset = return_series(
        ["2026-01-01", "2026-01-02", "2026-01-03"],
        [0.10, 0.05, -0.02],
    )
    benchmark = return_series(
        ["2026-01-01", "2026-01-02", "2026-01-03"],
        [0.04, 0.03, -0.01],
    )
    active = pd.Series([0.06, 0.02, -0.01])

    actual = calculate_annualized_tracking_error(
        asset, benchmark, "NVDA", "SPY", periods_per_year=12
    )

    assert actual == pytest.approx(active.std(ddof=1) * sqrt(12))


def test_identical_returns_have_zero_tracking_error() -> None:
    asset = return_series(["2026-01-01", "2026-01-02"], [0.10, -0.05])
    benchmark = asset.copy(deep=True)

    actual = calculate_annualized_tracking_error(asset, benchmark, "A", "B")

    assert actual == pytest.approx(0.0)


def test_single_observation_tracking_error_is_undefined() -> None:
    asset = return_series(["2026-01-01"], [0.10])
    benchmark = return_series(["2026-01-01"], [0.05])

    actual = calculate_annualized_tracking_error(asset, benchmark, "A", "B")

    assert np.isnan(actual)


@pytest.mark.parametrize("periods", [0, -1])
def test_rejects_non_positive_periods_per_year(periods) -> None:
    returns = return_series(["2026-01-01", "2026-01-02"], [0.10, 0.05])

    with pytest.raises(ValueError, match="positive"):
        calculate_annualized_tracking_error(returns, returns, "A", "B", periods)


@pytest.mark.parametrize("periods", [252.0, True, "252"])
def test_rejects_non_integer_periods_per_year(periods) -> None:
    returns = return_series(["2026-01-01", "2026-01-02"], [0.10, 0.05])

    with pytest.raises(TypeError, match="integer"):
        calculate_annualized_tracking_error(returns, returns, "A", "B", periods)


def test_correlation_detects_perfect_positive_and_negative_relationships() -> None:
    dates = ["2026-01-01", "2026-01-02", "2026-01-03"]
    a = return_series(dates, [0.01, 0.02, 0.03])
    b = return_series(dates, [0.02, 0.04, 0.06])
    c = return_series(dates, [-0.01, -0.02, -0.03])

    actual = calculate_return_correlation({"a": a, "b": b, "c": c})

    assert actual.columns.tolist() == ["A", "B", "C"]
    assert actual.index.tolist() == ["A", "B", "C"]
    assert actual.loc["A", "A"] == pytest.approx(1.0)
    assert actual.loc["A", "B"] == pytest.approx(1.0)
    assert actual.loc["A", "C"] == pytest.approx(-1.0)
    assert_frame_equal(actual, actual.T)


def test_correlation_uses_one_common_sample_for_every_pair() -> None:
    a = return_series(
        ["2026-01-01", "2026-01-02", "2026-01-03"],
        [-0.90, 0.01, 0.02],
    )
    b = return_series(
        ["2026-01-01", "2026-01-02", "2026-01-03"],
        [0.90, 0.02, 0.04],
    )
    c = return_series(["2026-01-02", "2026-01-03"], [0.03, 0.06])

    actual = calculate_return_correlation({"A": a, "B": b, "C": c})

    assert actual.loc["A", "B"] == pytest.approx(1.0)


def test_constant_series_has_undefined_pearson_correlation() -> None:
    dates = ["2026-01-01", "2026-01-02", "2026-01-03"]
    constant = return_series(dates, [0.01, 0.01, 0.01])
    changing = return_series(dates, [0.01, 0.02, 0.03])

    actual = calculate_return_correlation({"CONST": constant, "CHANGE": changing})

    assert actual.loc["CONST"].isna().all()
    assert actual["CONST"].isna().all()
    assert actual.loc["CHANGE", "CHANGE"] == pytest.approx(1.0)


def test_correlation_does_not_mutate_inputs() -> None:
    dates = ["2026-01-01", "2026-01-02"]
    a = return_series(dates, [0.01, 0.02], "old")
    b = return_series(dates, [0.02, 0.04])
    original_a = a.copy(deep=True)
    original_b = b.copy(deep=True)

    calculate_return_correlation({"A": a, "B": b})

    assert_series_equal(a, original_a)
    assert_series_equal(b, original_b)


def test_correlation_reuses_alignment_validation() -> None:
    valid = return_series(["2026-01-01", "2026-01-02"], [0.01, 0.02])
    invalid = return_series(["2026-01-01", "2026-01-02"], [0.01, np.inf])

    with pytest.raises(ValueError):
        calculate_return_correlation({"A": valid, "B": invalid})
    with pytest.raises(ValueError, match="At least one"):
        calculate_return_correlation({})
    with pytest.raises(ValueError, match="unique"):
        calculate_return_correlation({"a": valid, " A ": valid})
