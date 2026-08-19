"""收益统计的确定性离线测试。Deterministic return-statistics tests."""

from __future__ import annotations

from math import sqrt

import numpy as np
import pandas as pd
import pytest

from research.statistics import (
    TRADING_DAYS_PER_YEAR,
    ReturnStatistics,
    summarize_returns,
)


def test_summarizes_basic_statistics_and_geometric_annual_return() -> None:
    returns = pd.Series([np.nan, 0.10, 0.10], name="simple_return")

    result = summarize_returns(returns, periods_per_year=2)

    assert isinstance(result, ReturnStatistics)
    assert result.observation_count == 2
    assert result.mean_return == pytest.approx(0.10)
    assert result.standard_deviation == pytest.approx(0.0)
    assert result.minimum_return == pytest.approx(0.10)
    assert result.maximum_return == pytest.approx(0.10)
    assert result.cumulative_return == pytest.approx(0.21)
    assert result.annualized_return == pytest.approx(0.21)
    assert result.annualized_volatility == pytest.approx(0.0)


def test_annualizes_volatility_with_square_root_of_252() -> None:
    returns = pd.Series([np.nan, -0.01, 0.01], name="simple_return")
    daily_sample_std = returns.dropna().std(ddof=1)

    result = summarize_returns(returns)

    assert TRADING_DAYS_PER_YEAR == 252
    assert result.annualized_volatility == pytest.approx(
        daily_sample_std * sqrt(252)
    )


def test_geometric_annualization_uses_compounded_growth() -> None:
    returns = pd.Series([0.10, -0.10], name="simple_return")

    result = summarize_returns(returns, periods_per_year=4)

    expected_cumulative = (1.10 * 0.90) - 1.0
    expected_annualized = (1.0 + expected_cumulative) ** (4 / 2) - 1.0
    assert result.cumulative_return == pytest.approx(expected_cumulative)
    assert result.annualized_return == pytest.approx(expected_annualized)


def test_single_valid_observation_has_undefined_sample_volatility() -> None:
    result = summarize_returns(pd.Series([np.nan, 0.05]))

    assert result.observation_count == 1
    assert np.isnan(result.standard_deviation)
    assert np.isnan(result.annualized_volatility)


@pytest.mark.parametrize("returns", [pd.Series(dtype="float64"), pd.Series([np.nan])])
def test_empty_observations_return_explicit_undefined_statistics(returns) -> None:
    result = summarize_returns(returns)

    assert result.observation_count == 0
    assert all(
        np.isnan(value)
        for field, value in vars(result).items()
        if field != "observation_count"
    )


@pytest.mark.parametrize("periods", [0, -1])
def test_rejects_non_positive_periods_per_year(periods) -> None:
    with pytest.raises(ValueError, match="positive"):
        summarize_returns(pd.Series([0.01]), periods)


@pytest.mark.parametrize("periods", [252.0, True, "252"])
def test_rejects_non_integer_periods_per_year(periods) -> None:
    with pytest.raises(TypeError, match="integer"):
        summarize_returns(pd.Series([0.01]), periods)


def test_summary_rejects_invalid_return_series_consistently() -> None:
    with pytest.raises(ValueError):
        summarize_returns(pd.Series([0.01, np.nan, 0.02]))
