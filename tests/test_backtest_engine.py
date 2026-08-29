"""Daily lifecycle, no-look-ahead, and end-to-end backtest tests."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from backtest import BacktestEngine, ExecutionCosts
from portfolio import FixedQuantitySizing
from strategies import MovingAverageCrossoverStrategy
from trading import (
    AssetClass,
    ExecutionRejectionReason,
    InstrumentId,
    OrderSide,
    PlanningDecision,
)


NVDA = InstrumentId(AssetClass.EQUITY, "NVDA")


def market_data(
    closes: list[float],
    *,
    opens: list[float] | None = None,
) -> pd.DataFrame:
    actual_opens = closes if opens is None else opens
    highs = [max(open_, close) + 1.0 for open_, close in zip(actual_opens, closes)]
    lows = [max(0.0, min(open_, close) - 1.0) for open_, close in zip(actual_opens, closes)]
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
            "open": actual_opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [100.0] * len(closes),
        }
    ).astype({column: "float64" for column in ("open", "high", "low", "close", "volume")})


def engine(
    quantity: int = 10,
    *,
    commission: str = "0",
    slippage_bps: str = "0",
) -> BacktestEngine:
    return BacktestEngine(
        FixedQuantitySizing(quantity),
        ExecutionCosts(Decimal(commission), Decimal(slippage_bps)),
    )


def test_daily_lifecycle_is_close_decision_then_next_open_fill() -> None:
    data = market_data([1, 2, 3, 2, 1], opens=[1, 2, 30, 40, 50])
    result = engine().run(
        data,
        MovingAverageCrossoverStrategy(1, 2),
        NVDA,
        initial_cash=Decimal("1000"),
    )

    assert [plan.decision for plan in result.plans] == [
        PlanningDecision.INTENT_UNAVAILABLE,
        PlanningDecision.ORDER_REQUIRED,
        PlanningDecision.TARGET_ALREADY_SATISFIED,
        PlanningDecision.ORDER_REQUIRED,
        PlanningDecision.TARGET_ALREADY_SATISFIED,
    ]
    assert [order.side for order in result.orders] == [OrderSide.BUY, OrderSide.SELL]
    assert [fill.filled_at.date().isoformat() for fill in result.fills] == [
        "2026-01-03",
        "2026-01-05",
    ]
    assert [fill.price for fill in result.fills] == [Decimal("30.0"), Decimal("50.0")]

    # Day 2 closes before its BUY can execute; Day 3 snapshot includes the open fill.
    assert result.snapshots[1].positions == ()
    assert result.snapshots[2].positions[0].quantity == 10
    assert result.snapshots[2].cash == Decimal("700.0")
    assert result.snapshots[2].equity == Decimal("730.0")
    assert result.snapshots[-1].positions == ()
    assert result.snapshots[-1].cash == Decimal("1200.0")


def test_no_same_close_fill_even_when_close_differs_from_next_open() -> None:
    data = market_data([1, 2, 3], opens=[1, 2, 99])
    result = engine(1).run(
        data,
        MovingAverageCrossoverStrategy(1, 2),
        NVDA,
        initial_cash=Decimal("1000"),
    )
    assert result.orders[0].created_at.date().isoformat() == "2026-01-02"
    assert result.fills[0].filled_at.date().isoformat() == "2026-01-03"
    assert result.fills[0].price == Decimal("99.0")
    assert result.fills[0].price != Decimal("2.0")


def test_final_bar_order_is_rejected_for_no_next_bar() -> None:
    result = engine().run(
        market_data([1, 2]),
        MovingAverageCrossoverStrategy(1, 2),
        NVDA,
        initial_cash=Decimal("1000"),
    )
    assert len(result.orders) == 1
    assert not result.fills
    assert result.rejections[0].reason is ExecutionRejectionReason.NO_NEXT_BAR


def test_insufficient_cash_rejects_fill_and_preserves_state() -> None:
    result = engine(10).run(
        market_data([1, 2, 3], opens=[1, 2, 30]),
        MovingAverageCrossoverStrategy(1, 2),
        NVDA,
        initial_cash=Decimal("100"),
    )
    assert result.rejections[0].reason is ExecutionRejectionReason.INSUFFICIENT_CASH
    assert result.snapshots[-1].cash == Decimal("100")
    assert result.snapshots[-1].positions == ()


def test_all_warmup_produces_snapshots_but_no_orders() -> None:
    result = engine().run(
        market_data([1, 2, 3]),
        MovingAverageCrossoverStrategy(2, 5),
        NVDA,
        initial_cash=Decimal("1000"),
    )
    assert len(result.snapshots) == 3
    assert not result.orders
    assert not result.fills
    assert all(
        plan.decision is PlanningDecision.INTENT_UNAVAILABLE
        for plan in result.plans
    )


def test_engine_is_deterministic_and_does_not_mutate_input() -> None:
    data = market_data([1, 2, 3, 2, 1], opens=[1, 2, 30, 40, 50])
    original = data.copy(deep=True)
    strategy = MovingAverageCrossoverStrategy(1, 2)
    first = engine().run(data, strategy, NVDA, initial_cash=Decimal("1000"))
    second = engine().run(data, strategy, NVDA, initial_cash=Decimal("1000"))
    assert first == second
    assert_frame_equal(data, original)


def test_future_mutation_does_not_change_historical_decisions_or_fills() -> None:
    data = market_data([1, 2, 3, 2, 1], opens=[1, 2, 30, 40, 50])
    future_changed = data.copy(deep=True)
    future_changed.loc[4, ["open", "high", "low", "close"]] = [
        500,
        501,
        499,
        500,
    ]
    strategy = MovingAverageCrossoverStrategy(1, 2)
    original = engine().run(data, strategy, NVDA, initial_cash=Decimal("1000"))
    changed = engine().run(
        future_changed, strategy, NVDA, initial_cash=Decimal("1000")
    )
    assert original.plans[:4] == changed.plans[:4]
    assert original.orders[:2] == changed.orders[:2]
    assert original.fills[:1] == changed.fills[:1]
    assert original.snapshots[:4] == changed.snapshots[:4]


def test_appending_future_bars_does_not_change_existing_history() -> None:
    short = market_data([1, 2, 3], opens=[1, 2, 30])
    long = market_data([1, 2, 3, 100], opens=[1, 2, 30, 100])
    strategy = MovingAverageCrossoverStrategy(1, 2)
    short_result = engine().run(short, strategy, NVDA, initial_cash=Decimal("1000"))
    long_result = engine().run(long, strategy, NVDA, initial_cash=Decimal("1000"))
    assert short_result.plans == long_result.plans[:3]
    assert short_result.fills == long_result.fills[: len(short_result.fills)]
    assert short_result.snapshots == long_result.snapshots[:3]


def test_equity_curve_is_numeric_view_of_precise_snapshots() -> None:
    result = engine().run(
        market_data([1, 2, 3], opens=[1, 2, 30]),
        MovingAverageCrossoverStrategy(1, 2),
        NVDA,
        initial_cash=Decimal("1000"),
    )
    expected = pd.Series(
        [1000.0, 1000.0, 730.0],
        index=pd.date_range("2026-01-01", periods=3, freq="D", name="date"),
        name="equity",
    )
    assert_series_equal(result.equity_curve(), expected, check_freq=False)


def test_costs_are_reflected_in_end_to_end_cash() -> None:
    result = engine(2, commission="1", slippage_bps="10").run(
        market_data([1, 2, 3, 2, 1], opens=[1, 2, 100, 40, 100]),
        MovingAverageCrossoverStrategy(1, 2),
        NVDA,
        initial_cash=Decimal("1000"),
    )
    assert result.fills[0].price == Decimal("100") * Decimal("1.001")
    assert result.fills[1].price == Decimal("100") * Decimal("0.999")
    assert result.snapshots[-1].cash == Decimal("997.600")
