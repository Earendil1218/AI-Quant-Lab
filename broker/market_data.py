"""通过 IBKR 获取并转换历史市场数据。"""

from __future__ import annotations

import pandas as pd
from ib_insync import IB, Stock, util


def fetch_stock_history(
    ib: IB,
    symbol: str,
    duration: str = "1 Y",
    bar_size: str = "1 day",
) -> pd.DataFrame:
    """获取指定美股在常规交易时段内的历史成交 K 线。"""
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)

    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=duration,
        barSizeSetting=bar_size,
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
        keepUpToDate=False,
    )
    history = util.df(bars)

    if history is None or history.empty:
        raise RuntimeError(
            "未返回历史数据。请确认 TWS 已登录且账户具备历史数据权限。"
        )

    return history
