"""Immutable backtest records and numeric analytics views."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from portfolio.state import PortfolioSnapshot
from trading.fills import ExecutionRejection, Fill
from trading.orders import OrderPlan, OrderRequest


@dataclass(frozen=True)
class BacktestResult:
    plans: tuple[OrderPlan, ...]
    orders: tuple[OrderRequest, ...]
    fills: tuple[Fill, ...]
    rejections: tuple[ExecutionRejection, ...]
    snapshots: tuple[PortfolioSnapshot, ...]

    def equity_curve(self) -> pd.Series:
        """Return a float64 analytics view while records retain Decimal values."""
        return pd.Series(
            [float(snapshot.equity) for snapshot in self.snapshots],
            index=pd.DatetimeIndex(
                [snapshot.observed_at for snapshot in self.snapshots],
                name="date",
            ),
            name="equity",
            dtype="float64",
        )
