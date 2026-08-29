"""Deterministic execution cost and feasibility tests."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from backtest import ExecutionCosts, simulate_next_open_execution
from portfolio import PortfolioState
from trading import (
    AssetClass,
    ExecutionRejection,
    ExecutionRejectionReason,
    Fill,
    InstrumentId,
    OrderRequest,
    OrderSide,
)


NOW = datetime(2026, 1, 2)
NVDA = InstrumentId(AssetClass.EQUITY, "NVDA")


def request(side: OrderSide, quantity: int = 2) -> OrderRequest:
    return OrderRequest(NVDA, side, quantity, datetime(2026, 1, 1))


def test_buy_uses_next_open_plus_slippage_and_fixed_commission() -> None:
    outcome = simulate_next_open_execution(
        request(OrderSide.BUY),
        open_price=100.0,
        filled_at=NOW,
        portfolio=PortfolioState(Decimal("1000")),
        costs=ExecutionCosts(Decimal("1"), Decimal("10")),
    )
    assert isinstance(outcome, Fill)
    assert outcome.price == Decimal("100.0") * Decimal("1.001")
    assert outcome.commission == Decimal("1")


def test_sell_uses_next_open_minus_slippage() -> None:
    portfolio = PortfolioState(Decimal("1000"))
    portfolio.apply_fill(Fill(NVDA, OrderSide.BUY, 2, NOW, Decimal("10"), Decimal("0")))
    outcome = simulate_next_open_execution(
        request(OrderSide.SELL),
        open_price=100.0,
        filled_at=NOW,
        portfolio=portfolio,
        costs=ExecutionCosts(Decimal("1"), Decimal("10")),
    )
    assert isinstance(outcome, Fill)
    assert outcome.price == Decimal("100.0") * Decimal("0.999")


def test_insufficient_cash_is_execution_rejection_without_mutation() -> None:
    portfolio = PortfolioState(Decimal("100"))
    outcome = simulate_next_open_execution(
        request(OrderSide.BUY),
        open_price=100.0,
        filled_at=NOW,
        portfolio=portfolio,
        costs=ExecutionCosts(),
    )
    assert isinstance(outcome, ExecutionRejection)
    assert outcome.reason is ExecutionRejectionReason.INSUFFICIENT_CASH
    assert portfolio.cash == Decimal("100")
    assert portfolio.quantity_for(NVDA) == 0


def test_simulated_sell_cannot_exceed_current_position() -> None:
    with pytest.raises(ValueError, match="exceed"):
        simulate_next_open_execution(
            request(OrderSide.SELL),
            open_price=100.0,
            filled_at=NOW,
            portfolio=PortfolioState(Decimal("1000")),
            costs=ExecutionCosts(),
        )


@pytest.mark.parametrize("value", [Decimal("-1"), Decimal("Infinity")])
def test_execution_costs_must_be_finite_and_non_negative(value) -> None:
    with pytest.raises(ValueError):
        ExecutionCosts(fixed_commission=value)


def test_slippage_cannot_remove_the_entire_sell_price() -> None:
    with pytest.raises(ValueError, match="less than 10000"):
        ExecutionCosts(slippage_bps=Decimal("10000"))


def test_accounting_boundary_rejects_float_cost_configuration() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        ExecutionCosts(fixed_commission=1.0)
