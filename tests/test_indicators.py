"""Moving-average indicator contracts and validation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from research import calculate_moving_average


def market_data(closes: list[object]) -> pd.DataFrame:
    numeric = [float(value) if value is not None else value for value in closes]
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
            "open": numeric,
            "high": numeric,
            "low": numeric,
            "close": pd.Series(numeric, dtype="float64"),
            "volume": [100.0] * len(closes),
        }
    )


def test_moving_average_uses_trailing_complete_windows() -> None:
    actual = calculate_moving_average(market_data([1, 2, 3, 4]), 3)
    expected = pd.Series(
        [np.nan, np.nan, 2.0, 3.0],
        index=pd.date_range("2026-01-01", periods=4, freq="D", name="date"),
        name="close_moving_average_3",
    )
    assert_series_equal(actual, expected, check_freq=False)


def test_window_larger_than_history_is_explicitly_unavailable() -> None:
    actual = calculate_moving_average(market_data([1, 2]), 3)
    assert actual.isna().all()


def test_indicator_preserves_input() -> None:
    frame = market_data([1, 2, 3])
    original = frame.copy(deep=True)
    calculate_moving_average(frame, 2)
    assert_frame_equal(frame, original)


@pytest.mark.parametrize("window", [True, 2.0, "2"])
def test_indicator_rejects_non_integer_window(window) -> None:
    with pytest.raises(TypeError, match="integer"):
        calculate_moving_average(market_data([1, 2]), window)


@pytest.mark.parametrize("window", [0, -1])
def test_indicator_rejects_non_positive_window(window) -> None:
    with pytest.raises(ValueError, match="positive"):
        calculate_moving_average(market_data([1, 2]), window)


def test_indicator_reuses_market_data_validation() -> None:
    frame = market_data([1, 2, 3])
    with pytest.raises(TypeError, match="DataFrame"):
        calculate_moving_average([], 2)
    with pytest.raises(ValueError, match="必要字段"):
        calculate_moving_average(frame.drop(columns="volume"), 2)

    duplicate = frame.copy()
    duplicate.loc[2, "date"] = duplicate.loc[1, "date"]
    with pytest.raises(ValueError, match="重复"):
        calculate_moving_average(duplicate, 2)

    descending = frame.iloc[::-1]
    with pytest.raises(ValueError, match="升序"):
        calculate_moving_average(descending, 2)


@pytest.mark.parametrize("invalid", [np.nan, np.inf, -np.inf, "bad"])
def test_indicator_rejects_missing_or_non_finite_prices(invalid) -> None:
    frame = market_data([1, 2, 3])
    frame["close"] = frame["close"].astype("object")
    frame.loc[1, "close"] = invalid
    with pytest.raises(ValueError):
        calculate_moving_average(frame, 2)


def test_indicator_rejects_timezone_aware_daily_dates() -> None:
    frame = market_data([1, 2, 3])
    frame["date"] = frame["date"].dt.tz_localize("UTC")
    with pytest.raises(ValueError, match="timezone-naive"):
        calculate_moving_average(frame, 2)
