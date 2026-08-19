"""可复用的市场研究计算。Reusable market-research calculations."""

from research.returns import (
    calculate_cumulative_returns,
    calculate_log_returns,
    calculate_simple_returns,
)
from research.statistics import (
    TRADING_DAYS_PER_YEAR,
    ReturnStatistics,
    summarize_returns,
)

__all__ = [
    "calculate_cumulative_returns",
    "calculate_log_returns",
    "calculate_simple_returns",
    "ReturnStatistics",
    "summarize_returns",
    "TRADING_DAYS_PER_YEAR",
]
