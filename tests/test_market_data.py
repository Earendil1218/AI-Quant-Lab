"""配置、连接接口与历史市场数据模块的离线测试。"""

from __future__ import annotations

import inspect
import unittest
from datetime import date

from ib_insync import BarData

from broker.connection import connect_ibkr
from broker.market_data import fetch_stock_history
from config import settings


class FakeIB:
    """记录市场数据函数调用，但不建立网络连接。"""

    def __init__(self, bars: list[BarData]) -> None:
        self.bars = bars
        self.qualified_contract = None
        self.history_request = None

    def qualifyContracts(self, contract):
        self.qualified_contract = contract
        return [contract]

    def reqHistoricalData(self, contract, **kwargs):
        self.history_request = (contract, kwargs)
        return self.bars


class SettingsTests(unittest.TestCase):
    def test_default_settings_have_expected_types(self) -> None:
        self.assertIsInstance(settings.IBKR_HOST, str)
        self.assertIsInstance(settings.IBKR_PORT, int)
        self.assertIsInstance(settings.IBKR_CLIENT_ID, int)
        self.assertIsInstance(settings.DEFAULT_SYMBOL, str)
        self.assertIsInstance(settings.DEFAULT_DURATION, str)
        self.assertIsInstance(settings.DEFAULT_BAR_SIZE, str)


class PublicInterfaceTests(unittest.TestCase):
    def test_core_functions_are_callable(self) -> None:
        self.assertTrue(callable(connect_ibkr))
        self.assertTrue(callable(fetch_stock_history))

    def test_connect_ibkr_signature(self) -> None:
        signature = inspect.signature(connect_ibkr)

        self.assertEqual(
            list(signature.parameters),
            ["host", "port", "client_id", "timeout", "readonly"],
        )
        self.assertEqual(signature.parameters["timeout"].default, 10)
        self.assertIs(signature.parameters["readonly"].default, True)

    def test_fetch_stock_history_signature(self) -> None:
        signature = inspect.signature(fetch_stock_history)

        self.assertEqual(
            list(signature.parameters),
            ["ib", "symbol", "duration", "bar_size"],
        )
        self.assertEqual(signature.parameters["duration"].default, "1 Y")
        self.assertEqual(signature.parameters["bar_size"].default, "1 day")


class FetchStockHistoryTests(unittest.TestCase):
    def test_returns_dataframe_and_uses_expected_request(self) -> None:
        bar = BarData(
            date=date(2026, 8, 12),
            open=180.0,
            high=182.0,
            low=179.0,
            close=181.0,
            volume=1000,
            average=180.5,
            barCount=10,
        )
        ib = FakeIB([bar])

        history = fetch_stock_history(ib, "NVDA", "6 M", "1 day")

        self.assertFalse(history.empty)
        self.assertEqual(history.iloc[0]["close"], 181.0)
        self.assertEqual(ib.qualified_contract.symbol, "NVDA")
        self.assertEqual(ib.qualified_contract.exchange, "SMART")
        self.assertEqual(ib.qualified_contract.currency, "USD")

        _, request = ib.history_request
        self.assertEqual(
            request,
            {
                "endDateTime": "",
                "durationStr": "6 M",
                "barSizeSetting": "1 day",
                "whatToShow": "TRADES",
                "useRTH": True,
                "formatDate": 1,
                "keepUpToDate": False,
            },
        )

    def test_raises_runtime_error_for_empty_history(self) -> None:
        with self.assertRaises(RuntimeError):
            fetch_stock_history(FakeIB([]), "NVDA")


if __name__ == "__main__":
    unittest.main()
