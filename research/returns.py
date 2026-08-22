"""基于标准化收盘价计算收益率。Return calculations from normalized closes."""

from __future__ import annotations

import numpy as np
import pandas as pd

from data.validation import validate_market_data


def _validated_close(frame: pd.DataFrame) -> pd.Series:
    validate_market_data(frame)
    close = frame["close"].astype("float64")
    if (close <= 0).any():
        raise ValueError("close 必须严格大于零才能计算收益率。close must be strictly positive.")
    return close


def calculate_simple_returns(frame: pd.DataFrame) -> pd.Series:
    """
    计算 close 的简单价格收益率并保留首行 NaN。

    Calculate simple price returns from close and preserve the leading NaN.
    The result reflects the available close series; without adjusted prices it is
    not necessarily a total shareholder return.
    """
    close = _validated_close(frame)
    returns = close.pct_change(fill_method=None)
    returns.name = "simple_return"
    return returns.astype("float64")


def calculate_log_returns(frame: pd.DataFrame) -> pd.Series:
    """
    计算 close 的对数价格收益率并保留首行 NaN。

    Calculate log price returns from close and preserve the leading NaN. The
    result uses the available close series and does not assume corporate-action
    adjustments or dividend reinvestment.
    """
    close = _validated_close(frame)
    returns = np.log(close / close.shift(1))
    returns.name = "log_return"
    return returns.astype("float64")


def _validate_simple_return_series(returns: pd.Series) -> pd.Series:
    """Validate simple-return values while preserving an optional leading NaN."""
    if not isinstance(returns, pd.Series):
        raise TypeError("returns 必须是 pandas Series。returns must be a pandas Series.")

    numeric = pd.to_numeric(returns, errors="coerce").astype("float64")
    invalid_conversion = numeric.isna() & ~returns.isna()
    if invalid_conversion.any():
        raise ValueError("returns 必须只包含数值。returns must contain numeric values.")
    if np.isinf(numeric.to_numpy()).any():
        raise ValueError("returns 必须是有限数值。returns must contain finite values.")

    missing_positions = np.flatnonzero(numeric.isna().to_numpy())
    if len(missing_positions) and not (
        len(missing_positions) == 1 and missing_positions[0] == 0
    ):
        raise ValueError("returns 仅允许首项为 NaN。Only a leading NaN is allowed.")
    if (numeric.dropna() < -1).any():
        raise ValueError("简单收益率不得小于 -1。Simple returns cannot be below -1.")
    return numeric


def _validate_dated_simple_return_series(returns: pd.Series) -> pd.Series:
    """Validate non-empty simple returns with unambiguous daily date semantics."""
    numeric = _validate_simple_return_series(returns)
    if numeric.empty:
        raise ValueError("returns 不能为空。returns must not be empty.")
    if not isinstance(numeric.index, pd.DatetimeIndex):
        raise TypeError("returns 必须使用 DatetimeIndex。returns must use a DatetimeIndex.")
    if numeric.index.tz is not None:
        raise ValueError(
            "returns 日期不得包含时区。returns dates must be timezone-naive."
        )
    if numeric.index.has_duplicates:
        raise ValueError("returns 日期不得重复。returns dates must be unique.")
    if not numeric.index.is_monotonic_increasing:
        raise ValueError("returns 日期必须升序排列。returns dates must be ascending.")
    return numeric


def calculate_cumulative_returns(returns: pd.Series) -> pd.Series:
    """
    用复利计算简单收益率的累计序列，并保留可选的首行 NaN。

    Compound a simple-return Series, preserving an optional leading NaN.
    Missing values after the first observation are rejected rather than skipped.
    """
    numeric = _validate_simple_return_series(returns)

    cumulative = (1.0 + numeric).cumprod() - 1.0
    cumulative.name = "cumulative_return"
    return cumulative
