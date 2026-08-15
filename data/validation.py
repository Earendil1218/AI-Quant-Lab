"""市场数据 DataFrame 的基础质量验证。"""

from __future__ import annotations

import pandas as pd


REQUIRED_COLUMNS = ("date", "open", "high", "low", "close", "volume")
PRICE_COLUMNS = ("open", "high", "low", "close")


def validate_market_data(frame: pd.DataFrame) -> None:
    """验证市场数据结构、日期顺序和基础 OHLC 逻辑。"""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("市场数据必须是 pandas DataFrame。")

    if frame.empty:
        raise ValueError("市场数据不能为空。")

    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in frame.columns
    ]
    if missing_columns:
        raise ValueError(f"市场数据缺少必要字段：{', '.join(missing_columns)}")

    dates = pd.to_datetime(frame["date"], errors="coerce")
    if dates.isna().any():
        raise ValueError("date 字段包含缺失或无效日期。")
    if dates.duplicated().any():
        raise ValueError("date 字段包含重复日期。")
    if not dates.is_monotonic_increasing:
        raise ValueError("date 字段必须按升序排列。")

    if frame[list(PRICE_COLUMNS)].isna().any().any():
        raise ValueError("OHLC 价格字段包含缺失值。")

    numeric_prices = frame[list(PRICE_COLUMNS)].apply(
        pd.to_numeric,
        errors="coerce",
    )
    if numeric_prices.isna().any().any():
        raise ValueError("OHLC 价格字段必须是数值。")

    row_maximums = numeric_prices[["open", "low", "close"]].max(axis=1)
    if (numeric_prices["high"] < row_maximums).any():
        raise ValueError("high 必须不低于 open、low 和 close。")

    row_minimums = numeric_prices[["open", "high", "close"]].min(axis=1)
    if (numeric_prices["low"] > row_minimums).any():
        raise ValueError("low 必须不高于 open、high 和 close。")
