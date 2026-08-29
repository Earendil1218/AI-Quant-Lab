"""可复用的市场研究计算。Reusable market-research calculations."""

from research.alignment import (
    align_return_series,
    calculate_dated_simple_returns,
)
from research.comparison import (
    calculate_active_returns,
    calculate_annualized_tracking_error,
    calculate_return_correlation,
    compare_cumulative_performance,
)
from research.drawdown import (
    DrawdownSummary,
    calculate_drawdowns,
    calculate_wealth_index,
    summarize_drawdowns,
)
from research.indicators import calculate_moving_average
from research.returns import (
    calculate_cumulative_returns,
    calculate_log_returns,
    calculate_simple_returns,
)
from research.rolling import (
    calculate_rolling_annualized_volatility,
    calculate_rolling_compounded_returns,
)
from research.statistics import (
    TRADING_DAYS_PER_YEAR,
    ReturnStatistics,
    summarize_returns,
)

__all__ = [
    "align_return_series",
    "calculate_active_returns",
    "calculate_annualized_tracking_error",
    "calculate_cumulative_returns",
    "calculate_dated_simple_returns",
    "calculate_drawdowns",
    "calculate_log_returns",
    "calculate_moving_average",
    "calculate_rolling_annualized_volatility",
    "calculate_rolling_compounded_returns",
    "calculate_return_correlation",
    "calculate_simple_returns",
    "calculate_wealth_index",
    "compare_cumulative_performance",
    "DrawdownSummary",
    "ReturnStatistics",
    "summarize_returns",
    "summarize_drawdowns",
    "TRADING_DAYS_PER_YEAR",
]
