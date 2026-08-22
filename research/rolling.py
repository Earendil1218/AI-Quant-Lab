"""日期化收益率的完整窗口滚动指标。Complete-window rolling return metrics."""

from __future__ import annotations

from math import sqrt

import numpy as np
import pandas as pd

from research.returns import _validate_dated_simple_return_series
from research.statistics import TRADING_DAYS_PER_YEAR, _validate_periods_per_year


def _validate_window(window: int) -> None:
    if isinstance(window, bool) or not isinstance(window, int):
        raise TypeError("window 必须是整数。window must be an integer.")
    if window <= 0:
        raise ValueError("window 必须大于零。window must be positive.")


def _output_name(source_name: object, metric: str) -> str:
    return f"{source_name}_{metric}" if source_name is not None else metric


def calculate_rolling_compounded_returns(
    returns: pd.Series,
    window: int,
) -> pd.Series:
    """
    计算完整窗口内简单收益率的复合收益，不填充缺失观察值。

    Calculate compounded simple returns over complete windows without filling
    missing observations. An optional leading NaN is not a return observation.
    """
    numeric = _validate_dated_simple_return_series(returns)
    _validate_window(window)

    rolling_returns = numeric.rolling(window=window, min_periods=window).apply(
        lambda values: float(np.prod(1.0 + values) - 1.0),
        raw=True,
    )
    rolling_returns.name = _output_name(
        returns.name, "rolling_compounded_return"
    )
    return rolling_returns.astype("float64")


def calculate_rolling_annualized_volatility(
    returns: pd.Series,
    window: int,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> pd.Series:
    """
    用样本标准差计算完整窗口的年化波动率。

    Calculate complete-window annualized volatility using sample standard
    deviation (ddof=1) and an explicit periods-per-year assumption. A one-period
    sample volatility is undefined and therefore produces NaN.
    """
    numeric = _validate_dated_simple_return_series(returns)
    _validate_window(window)
    _validate_periods_per_year(periods_per_year)

    rolling_volatility = (
        numeric.rolling(window=window, min_periods=window).std(ddof=1)
        * sqrt(periods_per_year)
    )
    rolling_volatility.name = _output_name(
        returns.name, "rolling_annualized_volatility"
    )
    return rolling_volatility.astype("float64")
