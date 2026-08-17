"""将原始市场数据标准化为稳定的研究数据集。"""

from __future__ import annotations

import pandas as pd

from data.validation import validate_market_data


MARKET_DATA_COLUMNS = ("date", "open", "high", "low", "close", "volume")
NUMERIC_COLUMNS = ("open", "high", "low", "close", "volume")


def process_market_data(frame: pd.DataFrame) -> pd.DataFrame:
    """
    标准化市场数据，并返回不依赖数据源细节的新 DataFrame。

    Normalize market data into a new, source-independent DataFrame.

    Args:
        frame: 待处理的市场数据。Market data to normalize.

    Returns:
        具有稳定列顺序、类型和索引的数据。Data with a stable schema, dtypes,
        and index.

    Raises:
        TypeError: 输入不是 pandas DataFrame。The input is not a pandas DataFrame.
        ValueError: 数据无法安全标准化。The data cannot be normalized safely.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("市场数据必须是 pandas DataFrame。")

    missing_columns = [
        column for column in MARKET_DATA_COLUMNS if column not in frame.columns
    ]
    if missing_columns:
        raise ValueError(f"市场数据缺少必要字段：{', '.join(missing_columns)}")

    processed = frame.loc[:, MARKET_DATA_COLUMNS].copy(deep=True)
    normalized_dates = pd.to_datetime(
        processed["date"],
        errors="coerce",
        format="mixed",
    )
    if normalized_dates.isna().any():
        raise ValueError("date 字段包含缺失或无效日期。")
    if normalized_dates.dt.tz is not None:
        raise ValueError("日线 date 字段不得包含时区。")
    processed["date"] = normalized_dates.astype("datetime64[ns]")

    for column in NUMERIC_COLUMNS:
        processed[column] = pd.to_numeric(
            processed[column],
            errors="coerce",
        ).astype("float64")
    if processed.loc[:, NUMERIC_COLUMNS].isna().any().any():
        raise ValueError("OHLCV 字段包含缺失值或非数值。")

    processed = processed.sort_values("date", kind="stable").reset_index(drop=True)

    # 重复时间可能代表来源冲突；没有可信优先级时不得静默删除行情。
    # Duplicate timestamps may indicate source conflicts; never discard them silently.
    if processed["date"].duplicated().any():
        raise ValueError("date 字段包含重复日期，processing 不会自动删除记录。")

    validate_market_data(processed)
    return processed
