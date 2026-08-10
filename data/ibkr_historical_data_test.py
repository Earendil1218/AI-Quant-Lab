"""只读测试：通过本机 TWS 获取 NVDA 日线历史数据。"""

from __future__ import annotations

import os

import pandas as pd
from ib_insync import IB, Stock, util


HOST = os.getenv("IBKR_HOST", "127.0.0.1")
PORT = int(os.getenv("IBKR_PORT", "7497"))
CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "2"))
SYMBOL = "NVDA"


def fetch_stock_history(
    ib: IB,
    symbol: str,
    duration: str = "1 Y",
    bar_size: str = "1 day",
) -> pd.DataFrame:
    """获取指定美股的常规交易时段成交价历史 K 线。"""
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
    if history.empty:
        raise RuntimeError("未返回历史数据。请确认 TWS 已登录且账户具备历史数据权限。")
    return history


def main() -> None:
    ib = IB()
    try:
        print(f"连接 TWS 模拟账户：{HOST}:{PORT} ...")
        ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=10, readonly=True)
        print("连接成功。")

        history = fetch_stock_history(ib, SYMBOL)
        print(f"\n已获取 {SYMBOL} 日线历史数据：{len(history)} 条")
        print(f"日期范围：{history['date'].iloc[0]} 至 {history['date'].iloc[-1]}")
        print("\n最近 5 条：")
        print(history.tail().to_string(index=False))
    except Exception as exc:
        print(f"获取历史数据失败：{exc}")
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("\n已断开 TWS 连接。")


if __name__ == "__main__":
    main()
