"""市场数据基础质量验证测试。"""

from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from data.validation import validate_market_data


def valid_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-08-12", "2026-08-13"]),
            "open": [180.0, 181.0],
            "high": [182.0, 183.0],
            "low": [179.0, 180.0],
            "close": [181.0, 182.0],
            "volume": [1000, 1200],
        }
    )


def test_valid_market_data_passes_without_mutation() -> None:
    frame = valid_history()
    original = frame.copy(deep=True)

    assert validate_market_data(frame) is None
    assert_frame_equal(frame, original)


def test_rejects_non_dataframe() -> None:
    with pytest.raises(TypeError, match="pandas DataFrame"):
        validate_market_data([])


def test_rejects_empty_dataframe() -> None:
    with pytest.raises(ValueError, match="不能为空"):
        validate_market_data(pd.DataFrame())


@pytest.mark.parametrize(
    "missing_column",
    ["date", "open", "high", "low", "close", "volume"],
)
def test_rejects_missing_required_column(missing_column) -> None:
    frame = valid_history().drop(columns=missing_column)

    with pytest.raises(ValueError, match=missing_column):
        validate_market_data(frame)


def test_rejects_duplicate_dates() -> None:
    frame = valid_history()
    frame.loc[1, "date"] = frame.loc[0, "date"]

    with pytest.raises(ValueError, match="重复日期"):
        validate_market_data(frame)


def test_rejects_dates_not_in_ascending_order() -> None:
    frame = valid_history().iloc[::-1].reset_index(drop=True)

    with pytest.raises(ValueError, match="升序"):
        validate_market_data(frame)


@pytest.mark.parametrize("invalid_date", [None, "not-a-date"])
def test_rejects_missing_or_invalid_date(invalid_date) -> None:
    frame = valid_history()
    frame["date"] = frame["date"].astype(object)
    frame.loc[1, "date"] = invalid_date

    with pytest.raises(ValueError, match="无效日期"):
        validate_market_data(frame)


@pytest.mark.parametrize("price_column", ["open", "high", "low", "close"])
def test_rejects_missing_price(price_column) -> None:
    frame = valid_history()
    frame.loc[0, price_column] = None

    with pytest.raises(ValueError, match="缺失值"):
        validate_market_data(frame)


@pytest.mark.parametrize("price_column", ["open", "high", "low", "close"])
def test_rejects_non_numeric_price(price_column) -> None:
    frame = valid_history()
    frame[price_column] = frame[price_column].astype(object)
    frame.loc[0, price_column] = "invalid"

    with pytest.raises(ValueError, match="必须是数值"):
        validate_market_data(frame)


@pytest.mark.parametrize("invalid_volume", [None, "invalid"])
def test_rejects_missing_or_non_numeric_volume(invalid_volume) -> None:
    frame = valid_history()
    frame["volume"] = frame["volume"].astype(object)
    frame.loc[0, "volume"] = invalid_volume

    with pytest.raises(ValueError, match="OHLCV"):
        validate_market_data(frame)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("open", float("inf"), "有限数值"),
        ("volume", float("-inf"), "有限数值"),
        ("open", -1.0, "不得为负值"),
        ("volume", -1.0, "不得为负值"),
    ],
)
def test_rejects_infinite_or_negative_ohlcv(column, value, message) -> None:
    frame = valid_history()
    frame[column] = frame[column].astype("float64")
    frame.loc[0, column] = value

    with pytest.raises(ValueError, match=message):
        validate_market_data(frame)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("high", 179.5),
        ("high", 180.5),
        ("high", 178.5),
    ],
)
def test_rejects_high_below_open_close_or_low(column, value) -> None:
    frame = valid_history()
    frame.loc[0, column] = value

    with pytest.raises(ValueError, match="high 必须不低于"):
        validate_market_data(frame)


@pytest.mark.parametrize("value", [180.5, 181.5])
def test_rejects_low_above_open_or_close(value) -> None:
    frame = valid_history()
    frame.loc[0, "low"] = value

    with pytest.raises(ValueError, match="low 必须不高于"):
        validate_market_data(frame)
