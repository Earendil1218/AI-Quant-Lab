"""Broker-neutral trading-domain validation tests."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from trading import (
    AssetClass,
    ExecutionRejection,
    ExecutionRejectionReason,
    Fill,
    InstrumentId,
    OrderPlan,
    OrderRequest,
    OrderSide,
    PlanningDecision,
    TargetExposureIntent,
    TargetQuantity,
)


NOW = datetime(2026, 1, 1)
NVDA = InstrumentId(AssetClass.EQUITY, "NVDA")


def test_instrument_normalizes_symbol_and_is_hashable() -> None:
    instrument = InstrumentId(AssetClass.EQUITY, " nvda ")
    assert instrument.symbol == "NVDA"
    assert {instrument: 1}[NVDA] == 1


@pytest.mark.parametrize("symbol", ["", "   "])
def test_instrument_rejects_empty_symbol(symbol) -> None:
    with pytest.raises(ValueError, match="empty"):
        InstrumentId(AssetClass.EQUITY, symbol)


def test_target_exposure_is_not_quantity() -> None:
    intent = TargetExposureIntent(NVDA, NOW, 1.0, "test", "long")
    assert intent.target_exposure == 1.0
    assert not hasattr(intent, "quantity")


@pytest.mark.parametrize("exposure", [-1.0, 0.5, 2.0, float("inf")])
def test_phase_3e_rejects_unsupported_exposure(exposure) -> None:
    with pytest.raises(ValueError):
        TargetExposureIntent(NVDA, NOW, exposure, "test", "state")


def test_unavailable_intent_is_explicit() -> None:
    intent = TargetExposureIntent(NVDA, NOW, None, "test", "unavailable")
    assert intent.target_exposure is None


@pytest.mark.parametrize("quantity", [-1, True, 1.5])
def test_target_quantity_validation(quantity) -> None:
    with pytest.raises((TypeError, ValueError)):
        TargetQuantity(NVDA, NOW, quantity)


@pytest.mark.parametrize("quantity", [0, -1, True, 1.5])
def test_order_requires_positive_integer_quantity(quantity) -> None:
    with pytest.raises((TypeError, ValueError)):
        OrderRequest(NVDA, OrderSide.BUY, quantity, NOW)


def test_planning_decision_cannot_mix_order_presence() -> None:
    request = OrderRequest(NVDA, OrderSide.BUY, 1, NOW)
    with pytest.raises(ValueError):
        OrderPlan(PlanningDecision.ORDER_REQUIRED)
    with pytest.raises(ValueError):
        OrderPlan(PlanningDecision.TARGET_ALREADY_SATISFIED, request)


def test_fill_uses_decimal_accounting_values() -> None:
    fill = Fill(NVDA, OrderSide.BUY, 2, NOW, Decimal("100.10"), Decimal("1"))
    assert fill.price == Decimal("100.10")
    assert fill.commission == Decimal("1")


def test_fill_rejects_float_accounting_values() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        Fill(NVDA, OrderSide.BUY, 1, NOW, 100.0, Decimal("0"))


def test_execution_rejection_is_distinct_from_planning_decision() -> None:
    request = OrderRequest(NVDA, OrderSide.BUY, 1, NOW)
    rejection = ExecutionRejection(
        request, ExecutionRejectionReason.INSUFFICIENT_CASH, NOW
    )
    assert rejection.reason is ExecutionRejectionReason.INSUFFICIENT_CASH
    assert not isinstance(rejection.reason, PlanningDecision)
