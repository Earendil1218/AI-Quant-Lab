"""市场数据 CSV 存储的离线测试。"""

from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from config.settings import PROCESSED_DATA_DIR, RAW_DATA_DIR
from data.storage import (
    build_market_data_path,
    load_market_data,
    save_market_data,
)


def sample_history() -> pd.DataFrame:
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


def test_build_market_data_path_normalizes_symbol_and_daily_interval(tmp_path) -> None:
    path = build_market_data_path(" nvda ", " 1  DAY ", tmp_path)

    assert path == tmp_path / "NVDA_1d.csv"


def test_builds_distinct_raw_and_processed_paths() -> None:
    raw_path = build_market_data_path("NVDA", "1 day", RAW_DATA_DIR)
    processed_path = build_market_data_path("NVDA", "1 day", PROCESSED_DATA_DIR)

    assert raw_path == RAW_DATA_DIR / "NVDA_1d.csv"
    assert processed_path == PROCESSED_DATA_DIR / "NVDA_1d.csv"
    assert raw_path != processed_path


@pytest.mark.parametrize("symbol", ["", "   ", "NVDA/TEST", "../NVDA"])
def test_build_market_data_path_rejects_invalid_symbol(tmp_path, symbol) -> None:
    with pytest.raises(ValueError, match="无效的股票代码"):
        build_market_data_path(symbol, "1 day", tmp_path)


def test_build_market_data_path_rejects_unsupported_bar_size(tmp_path) -> None:
    with pytest.raises(ValueError, match="不支持的 K 线粒度"):
        build_market_data_path("NVDA", "5 mins", tmp_path)


def test_save_creates_parent_directories_and_returns_path(tmp_path) -> None:
    path = tmp_path / "nested" / "NVDA_1d.csv"

    saved_path = save_market_data(sample_history(), path)

    assert saved_path == path
    assert path.is_file()


def test_csv_round_trip_restores_date_column(tmp_path) -> None:
    expected = sample_history()
    path = tmp_path / "NVDA_1d.csv"

    save_market_data(expected, path)
    actual = load_market_data(path)

    assert pd.api.types.is_datetime64_any_dtype(actual["date"])
    assert_frame_equal(actual, expected, check_dtype=False)


def test_processed_csv_round_trip_uses_processed_directory(tmp_path) -> None:
    expected = sample_history()
    processed_directory = tmp_path / "processed"
    path = build_market_data_path("NVDA", "1 day", processed_directory)

    saved_path = save_market_data(expected, path)
    actual = load_market_data(saved_path)

    assert saved_path == processed_directory / "NVDA_1d.csv"
    assert_frame_equal(actual, expected, check_dtype=False)


def test_load_missing_file_raises_clear_error(tmp_path) -> None:
    path = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError, match="市场数据文件不存在"):
        load_market_data(path)
