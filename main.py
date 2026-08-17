"""AI-Quant-Lab 的 IBKR 历史数据测试入口。"""

from __future__ import annotations

import pandas as pd
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
    PROCESSED_DATA_DIR,
    RAW_DATA_DIR,
)
from data.processing import process_market_data
from data.storage import build_market_data_path, load_market_data, save_market_data
from data.validation import validate_market_data


def _date_bounds(history: pd.DataFrame) -> tuple[object, object]:
    """返回便于比较和展示的首尾日期。"""
    start = pd.Timestamp(history["date"].iloc[0]).date()
    end = pd.Timestamp(history["date"].iloc[-1]).date()
    return start, end


def main() -> None:
    """
    运行默认标的的只读历史数据处理流程。

    Run the read-only historical market data pipeline for the default symbol.
    """
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
        validate_market_data(history)

        raw_path = build_market_data_path(
            DEFAULT_SYMBOL,
            DEFAULT_BAR_SIZE,
            directory=RAW_DATA_DIR,
        )
        save_market_data(history, raw_path)

        processed_history = process_market_data(history)
        validate_market_data(processed_history)

        processed_path = build_market_data_path(
            DEFAULT_SYMBOL,
            DEFAULT_BAR_SIZE,
            directory=PROCESSED_DATA_DIR,
        )
        save_market_data(processed_history, processed_path)

        loaded_history = load_market_data(processed_path)
        validate_market_data(loaded_history)

        source_bounds = _date_bounds(processed_history)
        loaded_bounds = _date_bounds(loaded_history)
        if (
            len(loaded_history) != len(processed_history)
            or loaded_bounds != source_bounds
        ):
            raise RuntimeError("processed CSV 重载后的行数或日期范围不一致。")

        print(f"\n已获取并验证 {DEFAULT_SYMBOL} 原始数据：{len(history)} 条")
        print(f"日期范围：{source_bounds[0]} 至 {source_bounds[1]}")
        print(f"原始数据已保存至：{raw_path}")
        print(f"处理后数据已保存至：{processed_path}")
        print(f"处理后数据重载并验证成功：{len(loaded_history)} 条")
        print("\n最近 5 条：")
        print(loaded_history.tail().to_string(index=False))
    except Exception as exc:
        print(f"获取历史数据失败：{exc}")
    finally:
        if ib is not None and ib.isConnected():
            ib.disconnect()
            print("\n已断开 TWS 连接。")


if __name__ == "__main__":
    main()
