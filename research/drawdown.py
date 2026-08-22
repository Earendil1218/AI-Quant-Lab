"""基于简单收益率计算财富与回撤。Wealth and drawdown calculations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.returns import _validate_dated_simple_return_series


@dataclass(frozen=True)
class DrawdownSummary:
    """最大回撤区间的稳定输出。Stable output for a maximum-drawdown episode."""

    maximum_drawdown: float
    peak_date: pd.Timestamp
    trough_date: pd.Timestamp
    recovery_date: pd.Timestamp | None


def _validate_initial_value(initial_value: float) -> float:
    if isinstance(initial_value, (bool, np.bool_)) or not isinstance(
        initial_value, (int, float, np.integer, np.floating)
    ):
        raise TypeError(
            "initial_value 必须是数值。initial_value must be numeric."
        )
    normalized = float(initial_value)
    if not np.isfinite(normalized):
        raise ValueError(
            "initial_value 必须是有限数值。initial_value must be finite."
        )
    if normalized <= 0:
        raise ValueError(
            "initial_value 必须大于零。initial_value must be positive."
        )
    return normalized


def _output_name(source_name: object, metric: str) -> str:
    return f"{source_name}_{metric}" if source_name is not None else metric


def calculate_wealth_index(
    returns: pd.Series,
    initial_value: float = 1.0,
) -> pd.Series:
    """
    以复利计算财富指数；可选的首项 NaN 表示初始财富观察点。

    Compound simple returns into a wealth index. An optional leading NaN marks
    the initial wealth observation and is represented by ``initial_value``.
    """
    numeric = _validate_dated_simple_return_series(returns)
    starting_value = _validate_initial_value(initial_value)
    growth_factors = 1.0 + numeric
    if pd.isna(growth_factors.iloc[0]):
        growth_factors = growth_factors.copy()
        growth_factors.iloc[0] = 1.0

    wealth = starting_value * growth_factors.cumprod()
    wealth.name = _output_name(returns.name, "wealth_index")
    return wealth.astype("float64")


def calculate_drawdowns(
    returns: pd.Series,
    initial_value: float = 1.0,
) -> pd.Series:
    """计算财富相对历史高水位的回撤序列。Calculate drawdowns from high water marks."""
    wealth = calculate_wealth_index(returns, initial_value)
    running_peak = wealth.cummax()
    drawdowns = wealth / running_peak - 1.0
    drawdowns.name = _output_name(returns.name, "drawdown")
    return drawdowns.astype("float64")


def summarize_drawdowns(
    returns: pd.Series,
    initial_value: float = 1.0,
) -> DrawdownSummary:
    """
    汇总最早发生的最大回撤区间及其恢复日期。

    Summarize the earliest maximum-drawdown trough. Its peak is the last date at
    the previous high-water mark, and recovery is the first later date whose
    wealth is at least that peak. An unrecovered episode has no recovery date.
    """
    wealth = calculate_wealth_index(returns, initial_value)
    running_peak = wealth.cummax()
    drawdowns = wealth / running_peak - 1.0

    trough_date = pd.Timestamp(drawdowns.idxmin())
    maximum_drawdown = float(drawdowns.loc[trough_date])
    peak_value = float(running_peak.loc[trough_date])
    peak_candidates = wealth.loc[:trough_date]
    peak_date = pd.Timestamp(
        peak_candidates.index[peak_candidates.eq(peak_value)][-1]
    )

    if maximum_drawdown == 0.0:
        recovery_date: pd.Timestamp | None = trough_date
    else:
        after_trough = wealth.loc[wealth.index > trough_date]
        recovered = after_trough[after_trough >= peak_value]
        recovery_date = (
            pd.Timestamp(recovered.index[0]) if not recovered.empty else None
        )

    return DrawdownSummary(
        maximum_drawdown=maximum_drawdown,
        peak_date=peak_date,
        trough_date=trough_date,
        recovery_date=recovery_date,
    )
