"""市场数据标准化处理的离线测试。"""

from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from data.processing import MARKET_DATA_COLUMNS, process_market_data


def raw_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-08-13", "2026-08-12"],
            "open": ["181", "180"],
            "high": ["183", "182"],
            "low": ["180", "179"],
            "close": ["182", "181"],
            "volume": ["1200", "1000"],
            "average": [181.5, 180.5],
            "barCount": [12, 10],
        },
        index=[8, 4],
    )


def test_processes_market_data_into_stable_schema() -> None:
    processed = process_market_data(raw_history())

    assert tuple(processed.columns) == MARKET_DATA_COLUMNS
    assert processed["date"].tolist() == list(
        pd.to_datetime(["2026-08-12", "2026-08-13"])
    )
    assert isinstance(processed.index, pd.RangeIndex)
    assert processed.index.tolist() == [0, 1]
    assert pd.api.types.is_datetime64_ns_dtype(processed["date"])
    assert all(
        processed[column].dtype == "float64"
        for column in ("open", "high", "low", "close", "volume")
    )


def test_does_not_mutate_input_dataframe() -> None:
    frame = raw_history()
    original = frame.copy(deep=True)

    process_market_data(frame)

    assert_frame_equal(frame, original)


def test_rejects_non_dataframe() -> None:
    with pytest.raises(TypeError, match="pandas DataFrame"):
        process_market_data([])


def test_rejects_missing_required_column() -> None:
    frame = raw_history().drop(columns="volume")

    with pytest.raises(ValueError, match="volume"):
        process_market_data(frame)


@pytest.mark.parametrize("invalid_date", [None, "not-a-date"])
def test_rejects_missing_or_invalid_date(invalid_date) -> None:
    frame = raw_history()
    frame.loc[8, "date"] = invalid_date

    with pytest.raises(ValueError, match="无效日期"):
        process_market_data(frame)


def test_rejects_timezone_aware_daily_dates() -> None:
    frame = raw_history()
    frame["date"] = pd.to_datetime(frame["date"], utc=True)

    with pytest.raises(ValueError, match="不得包含时区"):
        process_market_data(frame)


@pytest.mark.parametrize("column", ["open", "high", "low", "close", "volume"])
def test_rejects_non_numeric_ohlcv(column) -> None:
    frame = raw_history()
    frame.loc[8, column] = "invalid"

    with pytest.raises(ValueError, match="OHLCV"):
        process_market_data(frame)


def test_rejects_duplicate_dates_without_silent_deduplication() -> None:
    frame = raw_history()
    frame.loc[8, "date"] = frame.loc[4, "date"]

    with pytest.raises(ValueError, match="不会自动删除"):
        process_market_data(frame)
