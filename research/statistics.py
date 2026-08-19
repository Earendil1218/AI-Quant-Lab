"""收益率的基础描述统计。Basic descriptive statistics for returns."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import numpy as np
import pandas as pd

from research.returns import calculate_cumulative_returns


TRADING_DAYS_PER_YEAR = 252
"""日线年化的市场惯例假设。Market-convention assumption for daily annualization."""


@dataclass(frozen=True)
class ReturnStatistics:
    """收益率统计的稳定输出。Stable output for return statistics."""

    observation_count: int
    mean_return: float
    standard_deviation: float
    minimum_return: float
    maximum_return: float
    cumulative_return: float
    annualized_return: float
    annualized_volatility: float


def _validate_periods_per_year(periods_per_year: int) -> None:
    if isinstance(periods_per_year, bool) or not isinstance(periods_per_year, int):
        raise TypeError("periods_per_year 必须是整数。periods_per_year must be an integer.")
    if periods_per_year <= 0:
        raise ValueError("periods_per_year 必须大于零。periods_per_year must be positive.")


def summarize_returns(
    returns: pd.Series,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> ReturnStatistics:
    """
    汇总简单收益率，并按明确频率假设计算几何年化收益和波动率。

    Summarize simple returns and calculate geometric annualized return and
    volatility under an explicit periods-per-year assumption. The default 252
    is a daily-market convention, not a natural constant. Results based on an
    unadjusted close series remain price-return statistics rather than total
    shareholder-return statistics.
    """
    _validate_periods_per_year(periods_per_year)
    cumulative = calculate_cumulative_returns(returns)
    observations = pd.to_numeric(returns, errors="coerce").dropna().astype("float64")
    count = int(observations.count())

    if count == 0:
        undefined = float("nan")
        return ReturnStatistics(
            observation_count=0,
            mean_return=undefined,
            standard_deviation=undefined,
            minimum_return=undefined,
            maximum_return=undefined,
            cumulative_return=undefined,
            annualized_return=undefined,
            annualized_volatility=undefined,
        )

    cumulative_return = float(cumulative.dropna().iloc[-1])
    standard_deviation = float(observations.std(ddof=1))
    annualized_return = float(
        (1.0 + cumulative_return) ** (periods_per_year / count) - 1.0
    )
    annualized_volatility = (
        standard_deviation * sqrt(periods_per_year)
        if not np.isnan(standard_deviation)
        else float("nan")
    )

    return ReturnStatistics(
        observation_count=count,
        mean_return=float(observations.mean()),
        standard_deviation=standard_deviation,
        minimum_return=float(observations.min()),
        maximum_return=float(observations.max()),
        cumulative_return=cumulative_return,
        annualized_return=annualized_return,
        annualized_volatility=float(annualized_volatility),
    )
