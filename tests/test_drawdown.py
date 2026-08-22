"""财富指数和回撤分析的确定性离线测试。Deterministic drawdown tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_series_equal

from research.drawdown import (
    DrawdownSummary,
    calculate_drawdowns,
    calculate_wealth_index,
    summarize_drawdowns,
)


def return_series(
    values: list[object],
    *,
    start: str = "2026-01-01",
    name: str | None = "NVDA",
) -> pd.Series:
    return pd.Series(
        values,
        index=pd.date_range(start, periods=len(values), freq="D", name="date"),
        name=name,
    )


def returns_from_wealth(values: list[float]) -> pd.Series:
    wealth = pd.Series(
        values,
        index=pd.date_range("2026-01-01", periods=len(values), freq="D", name="date"),
    )
    returns = wealth.pct_change(fill_method=None)
    returns.name = "ASSET"
    return returns


def test_wealth_index_compounds_monotonic_returns() -> None:
    actual = calculate_wealth_index(return_series([0.10, 0.10]))
    expected = return_series([1.10, 1.21], name="NVDA_wealth_index")

    assert_series_equal(actual, expected)


def test_wealth_index_compounds_mixed_returns() -> None:
    actual = calculate_wealth_index(return_series([0.20, -0.25]))

    assert actual.tolist() == pytest.approx([1.20, 0.90])


def test_wealth_index_uses_explicit_initial_value() -> None:
    actual = calculate_wealth_index(return_series([0.10]), initial_value=100.0)

    assert actual.iloc[0] == pytest.approx(110.0)


def test_leading_nan_represents_initial_wealth_observation() -> None:
    returns = return_series([np.nan, 0.05, -0.10])

    actual = calculate_wealth_index(returns, initial_value=100.0)

    assert actual.index.equals(returns.index)
    assert actual.tolist() == pytest.approx([100.0, 105.0, 94.5])


def test_total_loss_is_valid_and_wealth_cannot_revive() -> None:
    actual = calculate_wealth_index(return_series([0.10, -1.0, 5.0]))

    assert actual.tolist() == pytest.approx([1.10, 0.0, 0.0])


@pytest.mark.parametrize(
    "returns",
    [
        return_series([-1.01]),
        return_series([0.10, np.nan]),
        return_series([np.inf]),
        return_series(["invalid"]),
    ],
)
def test_wealth_index_rejects_invalid_returns(returns) -> None:
    with pytest.raises(ValueError):
        calculate_wealth_index(returns)


def test_wealth_index_rejects_empty_series() -> None:
    empty = pd.Series(index=pd.DatetimeIndex([], name="date"), dtype="float64")

    with pytest.raises(ValueError, match="empty"):
        calculate_wealth_index(empty)


@pytest.mark.parametrize("initial_value", [0, -1, np.inf, np.nan])
def test_rejects_non_positive_or_non_finite_initial_value(initial_value) -> None:
    with pytest.raises(ValueError):
        calculate_wealth_index(return_series([0.10]), initial_value)


@pytest.mark.parametrize("initial_value", [True, "1.0"])
def test_rejects_non_numeric_initial_value(initial_value) -> None:
    with pytest.raises(TypeError):
        calculate_wealth_index(return_series([0.10]), initial_value)


def test_wealth_index_does_not_mutate_input() -> None:
    returns = return_series([np.nan, 0.10, -0.05])
    original = returns.copy(deep=True)

    calculate_wealth_index(returns)

    assert_series_equal(returns, original)


def test_monotonic_growth_has_zero_drawdown() -> None:
    actual = calculate_drawdowns(return_series([np.nan, 0.10, 0.10]))

    assert actual.tolist() == pytest.approx([0.0, 0.0, 0.0])
    assert actual.name == "NVDA_drawdown"


def test_drawdown_falls_and_returns_to_zero_at_new_high() -> None:
    actual = calculate_drawdowns(returns_from_wealth([100, 120, 90, 130]))

    assert actual.tolist() == pytest.approx([0.0, 0.0, -0.25, 0.0])
    assert (actual <= 0.0).all()


def test_summary_identifies_peak_trough_and_recovery() -> None:
    returns = returns_from_wealth([100, 120, 90, 110, 120, 130])

    actual = summarize_drawdowns(returns)

    assert isinstance(actual, DrawdownSummary)
    assert actual.maximum_drawdown == pytest.approx(-0.25)
    assert actual.peak_date == pd.Timestamp("2026-01-02")
    assert actual.trough_date == pd.Timestamp("2026-01-03")
    assert actual.recovery_date == pd.Timestamp("2026-01-05")


def test_unrecovered_drawdown_has_no_recovery_date() -> None:
    actual = summarize_drawdowns(returns_from_wealth([100, 120, 90, 110]))

    assert actual.recovery_date is None


def test_equal_peaks_use_last_high_water_mark_before_decline() -> None:
    actual = summarize_drawdowns(returns_from_wealth([100, 120, 120, 100]))

    assert actual.peak_date == pd.Timestamp("2026-01-03")
    assert actual.trough_date == pd.Timestamp("2026-01-04")


def test_tied_maximum_drawdowns_use_earliest_trough() -> None:
    actual = summarize_drawdowns(returns_from_wealth([100, 80, 100, 80, 100]))

    assert actual.maximum_drawdown == pytest.approx(-0.20)
    assert actual.trough_date == pd.Timestamp("2026-01-02")
    assert actual.recovery_date == pd.Timestamp("2026-01-03")


def test_single_observation_has_no_drawdown() -> None:
    actual = summarize_drawdowns(return_series([np.nan]))

    assert actual.maximum_drawdown == pytest.approx(0.0)
    assert actual.peak_date == pd.Timestamp("2026-01-01")
    assert actual.trough_date == pd.Timestamp("2026-01-01")
    assert actual.recovery_date == pd.Timestamp("2026-01-01")


def test_total_loss_is_unrecovered_and_cannot_revive() -> None:
    actual = summarize_drawdowns(return_series([np.nan, 0.10, -1.0, 5.0]))

    assert actual.maximum_drawdown == pytest.approx(-1.0)
    assert actual.peak_date == pd.Timestamp("2026-01-02")
    assert actual.trough_date == pd.Timestamp("2026-01-03")
    assert actual.recovery_date is None


def test_rejects_ambiguous_date_indexes() -> None:
    range_index = pd.Series([0.10])
    duplicate = return_series([0.10, 0.20])
    duplicate.index = pd.DatetimeIndex(["2026-01-01", "2026-01-01"])
    descending = return_series([0.10, 0.20]).iloc[::-1]
    aware = return_series([0.10])
    aware.index = aware.index.tz_localize("UTC")

    with pytest.raises(TypeError, match="DatetimeIndex"):
        calculate_wealth_index(range_index)
    with pytest.raises(ValueError, match="unique"):
        calculate_wealth_index(duplicate)
    with pytest.raises(ValueError, match="ascending"):
        calculate_wealth_index(descending)
    with pytest.raises(ValueError, match="timezone-naive"):
        calculate_wealth_index(aware)
