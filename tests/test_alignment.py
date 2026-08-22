"""日期化收益率和多资产对齐的确定性离线测试。Date-aware alignment tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from research.alignment import align_return_series, calculate_dated_simple_returns


def price_history(
    dates: list[str] | None = None,
    prices: list[float] | None = None,
) -> pd.DataFrame:
    history_dates = (
        ["2026-08-17", "2026-08-18", "2026-08-19"]
        if dates is None
        else dates
    )
    closes = [100.0, 110.0, 121.0] if prices is None else prices
    return pd.DataFrame(
        {
            "date": pd.to_datetime(history_dates),
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1000.0] * len(closes),
        }
    )


def dated_returns(
    dates: list[str],
    values: list[float],
    name: str | None = None,
) -> pd.Series:
    return pd.Series(
        values,
        index=pd.DatetimeIndex(dates, name="date"),
        name=name,
        dtype="float64",
    )


def test_calculates_dated_returns_and_preserves_leading_nan() -> None:
    actual = calculate_dated_simple_returns(price_history(), " nvda ")
    expected = dated_returns(
        ["2026-08-17", "2026-08-18", "2026-08-19"],
        [np.nan, 0.1, 0.1],
        "NVDA",
    )

    assert_series_equal(actual, expected)


def test_dated_return_calculation_does_not_mutate_input() -> None:
    frame = price_history()
    original = frame.copy(deep=True)

    calculate_dated_simple_returns(frame, "NVDA")

    assert_frame_equal(frame, original)


@pytest.mark.parametrize("symbol", ["", "   "])
def test_rejects_empty_symbol(symbol) -> None:
    with pytest.raises(ValueError, match="symbol"):
        calculate_dated_simple_returns(price_history(), symbol)


def test_rejects_non_string_symbol() -> None:
    with pytest.raises(TypeError, match="symbol"):
        calculate_dated_simple_returns(price_history(), 123)


def test_aligns_on_exact_date_intersection_and_removes_leading_nan() -> None:
    nvda = dated_returns(
        ["2026-08-17", "2026-08-18", "2026-08-19"],
        [np.nan, 0.10, 0.20],
        "ignored_name",
    )
    spy = dated_returns(
        ["2026-08-18", "2026-08-19", "2026-08-20"],
        [np.nan, 0.01, 0.02],
    )

    actual = align_return_series({" nvda ": nvda, "spy": spy})
    expected = pd.DataFrame(
        {"NVDA": [0.20], "SPY": [0.01]},
        index=pd.DatetimeIndex(["2026-08-19"], name="date"),
    )

    assert_frame_equal(actual, expected)


def test_alignment_does_not_fill_missing_dates() -> None:
    nvda = dated_returns(["2026-08-18", "2026-08-20"], [0.10, 0.20])
    spy = dated_returns(["2026-08-18", "2026-08-19"], [0.01, 0.02])

    actual = align_return_series({"NVDA": nvda, "SPY": spy})

    assert actual.index.tolist() == [pd.Timestamp("2026-08-18")]
    assert not actual.isna().any().any()


def test_alignment_does_not_mutate_inputs() -> None:
    nvda = dated_returns(["2026-08-18", "2026-08-19"], [0.10, 0.20], "original")
    spy = dated_returns(["2026-08-18", "2026-08-19"], [0.01, 0.02])
    original_nvda = nvda.copy(deep=True)
    original_spy = spy.copy(deep=True)

    align_return_series({"NVDA": nvda, "SPY": spy})

    assert_series_equal(nvda, original_nvda)
    assert_series_equal(spy, original_spy)


def test_rejects_empty_mapping_and_non_mapping() -> None:
    with pytest.raises(ValueError, match="At least one"):
        align_return_series({})
    with pytest.raises(TypeError, match="Mapping"):
        align_return_series([])


def test_rejects_symbols_that_duplicate_after_normalization() -> None:
    returns = dated_returns(["2026-08-18"], [0.10])

    with pytest.raises(ValueError, match="unique"):
        align_return_series({"nvda": returns, " NVDA ": returns})


def test_rejects_non_datetime_index() -> None:
    returns = pd.Series([0.10], dtype="float64")

    with pytest.raises(TypeError, match="DatetimeIndex"):
        align_return_series({"NVDA": returns})


def test_rejects_timezone_aware_index() -> None:
    returns = pd.Series(
        [0.10],
        index=pd.DatetimeIndex(["2026-08-18"], tz="UTC"),
    )

    with pytest.raises(ValueError, match="timezone-naive"):
        align_return_series({"NVDA": returns})


def test_rejects_duplicate_or_descending_dates() -> None:
    duplicate = dated_returns(["2026-08-18", "2026-08-18"], [0.10, 0.20])
    descending = dated_returns(["2026-08-19", "2026-08-18"], [0.10, 0.20])

    with pytest.raises(ValueError, match="unique"):
        align_return_series({"NVDA": duplicate})
    with pytest.raises(ValueError, match="ascending"):
        align_return_series({"NVDA": descending})


@pytest.mark.parametrize(
    "returns",
    [
        dated_returns(["2026-08-18", "2026-08-19"], [0.10, np.nan]),
        dated_returns(["2026-08-18"], [np.inf]),
        dated_returns(["2026-08-18"], [-1.01]),
        pd.Series(
            ["invalid"],
            index=pd.DatetimeIndex(["2026-08-18"], name="date"),
        ),
    ],
)
def test_rejects_invalid_return_values(returns) -> None:
    with pytest.raises(ValueError):
        align_return_series({"NVDA": returns})


def test_rejects_series_with_no_common_dates() -> None:
    nvda = dated_returns(["2026-08-18"], [0.10])
    spy = dated_returns(["2026-08-19"], [0.01])

    with pytest.raises(ValueError, match="no common dates"):
        align_return_series({"NVDA": nvda, "SPY": spy})
