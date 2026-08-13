"""AI-Quant-Lab 的 IBKR 历史数据测试入口。"""

from __future__ import annotations

from ib_insync import IB

from broker.connection import connect_ibkr
from broker.market_data import fetch_stock_history
from config.settings import (
    DEFAULT_BAR_SIZE,
    DEFAULT_DURATION,
    DEFAULT_SYMBOL,
    IBKR_CLIENT_ID,
    IBKR_HOST,
    IBKR_PORT,
)


def main() -> None:
    """连接 TWS，获取默认标的的历史数据并输出测试结果。"""
    ib: IB | None = None

    try:
        print(f"连接 TWS Paper Trading：{IBKR_HOST}:{IBKR_PORT} ...")
        ib = connect_ibkr(
            host=IBKR_HOST,
            port=IBKR_PORT,
            client_id=IBKR_CLIENT_ID,
            readonly=True,
        )
        print("连接成功。")

        history = fetch_stock_history(
            ib=ib,
            symbol=DEFAULT_SYMBOL,
            duration=DEFAULT_DURATION,
            bar_size=DEFAULT_BAR_SIZE,
        )

        print(f"\n已获取 {DEFAULT_SYMBOL} 历史数据：{len(history)} 条")
        print(f"日期范围：{history['date'].iloc[0]} 至 {history['date'].iloc[-1]}")
        print("\n最近 5 条：")
        print(history.tail().to_string(index=False))
    except Exception as exc:
        print(f"获取历史数据失败：{exc}")
    finally:
        if ib is not None and ib.isConnected():
            ib.disconnect()
            print("\n已断开 TWS 连接。")


if __name__ == "__main__":
    main()
