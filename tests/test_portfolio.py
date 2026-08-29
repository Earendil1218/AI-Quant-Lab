"""Sizing, reconciliation, and precise fill-accounting tests."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from portfolio import (
    FixedQuantitySizing,
    PortfolioState,
    plan_target_order,
)
from trading import (
    AssetClass,
    Fill,
    InstrumentId,
    OrderSide,
    PlanningDecision,
    TargetExposureIntent,
)


NOW = datetime(2026, 1, 1)
NVDA = InstrumentId(AssetClass.EQUITY, "NVDA")


def intent(exposure: float | None) -> TargetExposureIntent:
    state = "unavailable" if exposure is None else "available"
    return TargetExposureIntent(NVDA, NOW, exposure, "test", state)


def fill(side: OrderSide, quantity: int, price: str, commission: str = "0") -> Fill:
    return Fill(NVDA, side, quantity, NOW, Decimal(price), Decimal(commission))


def test_fixed_sizing_maps_state_without_hardcoding_quantity_in_strategy() -> None:
    sizing = FixedQuantitySizing(10)
    assert sizing.size(intent(1.0)).quantity == 10
    assert sizing.size(intent(0.0)).quantity == 0
    assert sizing.size(intent(None)) is None


@pytest.mark.parametrize("quantity", [0, -1, True, 1.5])
def test_fixed_sizing_rejects_invalid_long_quantity(quantity) -> None:
    with pytest.raises((TypeError, ValueError)):
        FixedQuantitySizing(quantity)


def test_warmup_is_planning_no_trade() -> None:
    plan = plan_target_order(intent(None), FixedQuantitySizing(10), PortfolioState(Decimal("1000")))
    assert plan.decision is PlanningDecision.INTENT_UNAVAILABLE
    assert plan.request is None


def test_flat_to_long_plans_buy_and_repeated_long_does_not_trade() -> None:
    portfolio = PortfolioState(Decimal("1000"))
    sizing = FixedQuantitySizing(10)
    buy = plan_target_order(intent(1.0), sizing, portfolio)
    assert buy.request.side is OrderSide.BUY
    assert buy.request.quantity == 10
    portfolio.apply_fill(fill(OrderSide.BUY, 10, "20"))
    repeated = plan_target_order(intent(1.0), sizing, portfolio)
    assert repeated.decision is PlanningDecision.TARGET_ALREADY_SATISFIED


def test_long_to_flat_plans_sell() -> None:
    portfolio = PortfolioState(Decimal("1000"))
    portfolio.apply_fill(fill(OrderSide.BUY, 10, "20"))
    plan = plan_target_order(intent(0.0), FixedQuantitySizing(10), portfolio)
    assert plan.request.side is OrderSide.SELL
    assert plan.request.quantity == 10


def test_reconciliation_trades_only_the_difference_to_target_quantity() -> None:
    portfolio = PortfolioState(Decimal("1000"))
    portfolio.apply_fill(fill(OrderSide.BUY, 4, "20"))
    plan = plan_target_order(intent(1.0), FixedQuantitySizing(10), portfolio)
    assert plan.request.side is OrderSide.BUY
    assert plan.request.quantity == 6


def test_buy_and_sell_fills_update_cash_and_quantity_exactly() -> None:
    portfolio = PortfolioState(Decimal("1000"))
    portfolio.apply_fill(fill(OrderSide.BUY, 2, "100.10", "1"))
    assert portfolio.cash == Decimal("798.80")
    assert portfolio.quantity_for(NVDA) == 2
    portfolio.apply_fill(fill(OrderSide.SELL, 2, "99.90", "1"))
    assert portfolio.cash == Decimal("997.60")
    assert portfolio.quantity_for(NVDA) == 0


def test_order_request_does_not_change_portfolio() -> None:
    portfolio = PortfolioState(Decimal("1000"))
    plan_target_order(intent(1.0), FixedQuantitySizing(10), portfolio)
    assert portfolio.cash == Decimal("1000")
    assert portfolio.quantity_for(NVDA) == 0


def test_fill_cannot_create_short_or_negative_cash() -> None:
    portfolio = PortfolioState(Decimal("100"))
    with pytest.raises(ValueError, match="short"):
        portfolio.apply_fill(fill(OrderSide.SELL, 1, "10"))
    with pytest.raises(ValueError, match="negative cash"):
        portfolio.apply_fill(fill(OrderSide.BUY, 2, "100"))


def test_close_mark_creates_exact_equity_snapshot_without_average_cost() -> None:
    portfolio = PortfolioState(Decimal("1000"))
    portfolio.apply_fill(fill(OrderSide.BUY, 2, "100"))
    snapshot = portfolio.snapshot(NOW, {NVDA: Decimal("110")})
    assert snapshot.cash == Decimal("800")
    assert snapshot.market_value == Decimal("220")
    assert snapshot.equity == Decimal("1020")
    assert snapshot.positions[0].quantity == 2
    assert not hasattr(snapshot.positions[0], "average_cost")
