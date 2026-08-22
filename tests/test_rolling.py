"""完整窗口滚动研究指标的确定性测试。Deterministic rolling-metric tests."""

from __future__ import annotations

from math import sqrt

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_series_equal

from research.rolling import (
    calculate_rolling_annualized_volatility,
    calculate_rolling_compounded_returns,
)
from research.statistics import TRADING_DAYS_PER_YEAR


def return_series(
    values: list[object],
    *,
    name: str | None = "NVDA",
) -> pd.Series:
    return pd.Series(
        values,
        index=pd.date_range("2026-01-01", periods=len(values), freq="D", name="date"),
        name=name,
    )


def test_three_period_return_uses_compounding_not_addition() -> None:
    returns = return_series([0.10, -0.10, 0.10])

    actual = calculate_rolling_compounded_returns(returns, window=3)

    assert actual.iloc[:2].isna().all()
    assert actual.iloc[2] == pytest.approx(0.089)


def test_one_period_rolling_return_equals_input() -> None:
    returns = return_series([0.10, -0.20])

    actual = calculate_rolling_compounded_returns(returns, window=1)

    assert actual.tolist() == pytest.approx(returns.tolist())


def test_total_loss_compounds_to_negative_one() -> None:
    returns = return_series([0.10, -1.0, 0.50])

    actual = calculate_rolling_compounded_returns(returns, window=3)

    assert actual.iloc[-1] == pytest.approx(-1.0)


def test_leading_nan_is_not_a_return_observation() -> None:
    returns = return_series([np.nan, 0.10, -0.10, 0.10])

    actual = calculate_rolling_compounded_returns(returns, window=3)

    assert actual.iloc[:3].isna().all()
    assert actual.iloc[3] == pytest.approx(0.089)


def test_window_larger_than_observations_returns_all_nan() -> None:
    returns = return_series([np.nan, 0.10, 0.20])

    actual = calculate_rolling_compounded_returns(returns, window=3)

    assert actual.isna().all()
    assert actual.index.equals(returns.index)


def test_rolling_return_preserves_index_dtype_and_predictable_name() -> None:
    returns = return_series([0.10, 0.20], name="SPY")

    actual = calculate_rolling_compounded_returns(returns, window=2)

    assert actual.index.equals(returns.index)
    assert actual.dtype == "float64"
    assert actual.name == "SPY_rolling_compounded_return"


def test_rolling_return_does_not_mutate_input() -> None:
    returns = return_series([np.nan, 0.10, -0.05])
    original = returns.copy(deep=True)

    calculate_rolling_compounded_returns(returns, window=2)

    assert_series_equal(returns, original)


def test_rolling_volatility_uses_sample_std_and_annualization() -> None:
    returns = return_series([0.10, -0.10, 0.20])
    expected = returns.std(ddof=1) * sqrt(12)

    actual = calculate_rolling_annualized_volatility(
        returns,
        window=3,
        periods_per_year=12,
    )

    assert actual.iloc[:2].isna().all()
    assert actual.iloc[2] == pytest.approx(expected)


def test_default_volatility_annualizes_with_252() -> None:
    returns = return_series([-0.01, 0.01])
    expected = returns.std(ddof=1) * sqrt(TRADING_DAYS_PER_YEAR)

    actual = calculate_rolling_annualized_volatility(returns, window=2)

    assert actual.iloc[-1] == pytest.approx(expected)


def test_constant_return_window_has_zero_volatility() -> None:
    actual = calculate_rolling_annualized_volatility(
        return_series([0.05, 0.05, 0.05]),
        window=3,
    )

    assert actual.iloc[-1] == pytest.approx(0.0)


def test_leading_nan_delays_first_complete_volatility_window() -> None:
    returns = return_series([np.nan, -0.01, 0.01, 0.02])

    actual = calculate_rolling_annualized_volatility(returns, window=3)

    assert actual.iloc[:3].isna().all()
    assert actual.iloc[3] == pytest.approx(
        returns.iloc[1:].std(ddof=1) * sqrt(TRADING_DAYS_PER_YEAR)
    )


def test_one_period_sample_volatility_is_undefined() -> None:
    actual = calculate_rolling_annualized_volatility(
        return_series([0.10, -0.10]),
        window=1,
    )

    assert actual.isna().all()


def test_large_volatility_window_returns_all_nan() -> None:
    actual = calculate_rolling_annualized_volatility(
        return_series([0.10, -0.10]),
        window=3,
    )

    assert actual.isna().all()


def test_volatility_preserves_index_dtype_and_predictable_name() -> None:
    returns = return_series([0.10, -0.10], name=None)

    actual = calculate_rolling_annualized_volatility(returns, window=2)

    assert actual.index.equals(returns.index)
    assert actual.dtype == "float64"
    assert actual.name == "rolling_annualized_volatility"


@pytest.mark.parametrize("window", [0, -1])
def test_rejects_non_positive_window(window) -> None:
    with pytest.raises(ValueError, match="positive"):
        calculate_rolling_compounded_returns(return_series([0.10]), window)


@pytest.mark.parametrize("window", [1.5, True, "20"])
def test_rejects_non_integer_window(window) -> None:
    with pytest.raises(TypeError, match="integer"):
        calculate_rolling_compounded_returns(return_series([0.10]), window)


@pytest.mark.parametrize("periods", [0, -1])
def test_rejects_non_positive_periods_per_year(periods) -> None:
    with pytest.raises(ValueError, match="positive"):
        calculate_rolling_annualized_volatility(
            return_series([0.10, -0.10]), 2, periods
        )


@pytest.mark.parametrize("periods", [252.0, True, "252"])
def test_rejects_non_integer_periods_per_year(periods) -> None:
    with pytest.raises(TypeError, match="integer"):
        calculate_rolling_annualized_volatility(
            return_series([0.10, -0.10]), 2, periods
        )


@pytest.mark.parametrize(
    "returns",
    [
        return_series([0.10, np.nan]),
        return_series([np.nan, 0.10, np.nan]),
        return_series([np.inf]),
        return_series([-1.01]),
        return_series(["invalid"]),
    ],
)
def test_rejects_invalid_return_values(returns) -> None:
    with pytest.raises(ValueError):
        calculate_rolling_compounded_returns(returns, window=1)


def test_rejects_empty_series() -> None:
    empty = pd.Series(index=pd.DatetimeIndex([], name="date"), dtype="float64")

    with pytest.raises(ValueError, match="empty"):
        calculate_rolling_compounded_returns(empty, window=1)


def test_rejects_ambiguous_date_indexes() -> None:
    range_index = pd.Series([0.10])
    duplicate = return_series([0.10, 0.20])
    duplicate.index = pd.DatetimeIndex(["2026-01-01", "2026-01-01"])
    descending = return_series([0.10, 0.20]).iloc[::-1]
    aware = return_series([0.10])
    aware.index = aware.index.tz_localize("UTC")

    with pytest.raises(TypeError, match="DatetimeIndex"):
        calculate_rolling_compounded_returns(range_index, 1)
    with pytest.raises(ValueError, match="unique"):
        calculate_rolling_compounded_returns(duplicate, 1)
    with pytest.raises(ValueError, match="ascending"):
        calculate_rolling_compounded_returns(descending, 1)
    with pytest.raises(ValueError, match="timezone-naive"):
        calculate_rolling_compounded_returns(aware, 1)
