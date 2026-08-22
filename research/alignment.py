"""按交易日期构造和对齐资产收益率。Date-aware return construction and alignment."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from research.returns import _validate_simple_return_series, calculate_simple_returns


def _normalize_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise TypeError("symbol 必须是字符串。symbol must be a string.")
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol 不能为空。symbol must not be empty.")
    return normalized


def calculate_dated_simple_returns(
    frame: pd.DataFrame,
    symbol: str,
) -> pd.Series:
    """
    计算以无时区交易日期为索引的简单收益率，并保留首项 NaN。

    Calculate simple returns indexed by timezone-naive trading dates and preserve
    the leading NaN. The normalized symbol becomes the Series name.
    """
    normalized_symbol = _normalize_symbol(symbol)
    returns = calculate_simple_returns(frame)
    dates = pd.DatetimeIndex(frame["date"], name="date")
    if dates.tz is not None:
        raise ValueError(
            "日线收益日期不得包含时区。Daily return dates must be timezone-naive."
        )

    dated_returns = pd.Series(
        returns.to_numpy(copy=True),
        index=dates,
        name=normalized_symbol,
        dtype="float64",
    )
    return dated_returns


def _validate_return_series(symbol: str, returns: pd.Series) -> pd.Series:
    if not isinstance(returns, pd.Series):
        raise TypeError(
            f"{symbol} 的收益率必须是 pandas Series。"
            f"Returns for {symbol} must be a pandas Series."
        )
    if not isinstance(returns.index, pd.DatetimeIndex):
        raise TypeError(
            f"{symbol} 的收益率必须使用 DatetimeIndex。"
            f"Returns for {symbol} must use a DatetimeIndex."
        )
    if returns.index.tz is not None:
        raise ValueError(
            f"{symbol} 的日期不得包含时区。Dates for {symbol} must be timezone-naive."
        )
    if returns.index.has_duplicates:
        raise ValueError(
            f"{symbol} 的日期不得重复。Dates for {symbol} must be unique."
        )
    if not returns.index.is_monotonic_increasing:
        raise ValueError(
            f"{symbol} 的日期必须升序排列。Dates for {symbol} must be ascending."
        )

    numeric = _validate_simple_return_series(returns)

    missing_positions = np.flatnonzero(numeric.isna().to_numpy())
    if len(missing_positions) == 1:
        numeric = numeric.iloc[1:]
    numeric.name = symbol
    return numeric


def align_return_series(
    returns_by_symbol: Mapping[str, pd.Series],
) -> pd.DataFrame:
    """
    按共同日期交集对齐多个资产的简单收益率，不填充缺失观察值。

    Align simple-return Series on their exact date intersection without filling
    missing observations. Mapping keys are the authoritative asset identifiers;
    input Series names do not affect the output column names.
    """
    if not isinstance(returns_by_symbol, Mapping):
        raise TypeError(
            "returns_by_symbol 必须是 Mapping。returns_by_symbol must be a Mapping."
        )
    if not returns_by_symbol:
        raise ValueError(
            "至少需要一个资产收益率序列。At least one return Series is required."
        )

    validated: list[pd.Series] = []
    normalized_symbols: set[str] = set()
    for raw_symbol, returns in returns_by_symbol.items():
        symbol = _normalize_symbol(raw_symbol)
        if symbol in normalized_symbols:
            raise ValueError(
                f"标准化后的 symbol 不得重复：{symbol}。"
                f"Normalized symbols must be unique: {symbol}."
            )
        normalized_symbols.add(symbol)
        validated.append(_validate_return_series(symbol, returns))

    aligned = pd.concat(validated, axis="columns", join="inner").copy()
    aligned.index.name = "date"
    if aligned.empty:
        raise ValueError(
            "资产收益率没有共同日期。Return Series have no common dates."
        )
    return aligned.astype("float64")
