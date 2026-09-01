"""Deterministic broker-neutral pre-trade risk tests."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from portfolio import PortfolioState
from risk import (
    RiskConfiguration,
    RiskDecisionStatus,
    RiskRejectionReason,
    ValuationContext,
    evaluate_order_risk,
)
from trading import AssetClass, Fill, InstrumentId, OrderRequest, OrderSide


CREATED_AT = datetime(2026, 1, 1)
EVALUATED_AT = datetime(2026, 1, 2)
NVDA = InstrumentId(AssetClass.EQUITY, "NVDA")
SPY = InstrumentId(AssetClass.EQUITY, "SPY")


def request(side: OrderSide = OrderSide.BUY, quantity: int = 2) -> OrderRequest:
    return OrderRequest(NVDA, side, quantity, CREATED_AT)


def valuation(price: Decimal | None = Decimal("100")) -> ValuationContext:
    prices = {} if price is None else {NVDA: price}
    return ValuationContext(EVALUATED_AT, prices)


def evaluate(
    configuration: RiskConfiguration,
    *,
    order: OrderRequest | None = None,
    portfolio: PortfolioState | None = None,
    context: ValuationContext | None = None,
):
    return evaluate_order_risk(
        request() if order is None else order,
        PortfolioState(Decimal("1000")) if portfolio is None else portfolio,
        valuation() if context is None else context,
        configuration,
    )


def test_empty_configuration_approves_supported_long_order() -> None:
    decision = evaluate(RiskConfiguration())
    assert decision.status is RiskDecisionStatus.APPROVED
    assert decision.reason is None


def test_allowed_instruments_none_disables_rule_but_empty_set_blocks_all() -> None:
    decision = evaluate(RiskConfiguration(allowed_instruments=None))
    assert decision.status is RiskDecisionStatus.APPROVED
    decision = evaluate(RiskConfiguration(allowed_instruments=frozenset()))
    assert decision.reason is RiskRejectionReason.INSTRUMENT_NOT_ALLOWED


def test_allowed_instruments_uses_full_instrument_identity() -> None:
    allowed = evaluate(RiskConfiguration(allowed_instruments=frozenset({NVDA})))
    blocked = evaluate(RiskConfiguration(allowed_instruments=frozenset({SPY})))
    assert allowed.status is RiskDecisionStatus.APPROVED
    assert blocked.reason is RiskRejectionReason.INSTRUMENT_NOT_ALLOWED


def test_allowed_instruments_rejects_bare_symbols() -> None:
    with pytest.raises(TypeError, match="InstrumentId"):
        RiskConfiguration(allowed_instruments=frozenset({"NVDA"}))


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_quantity_limits_must_be_positive_integers(value) -> None:
    with pytest.raises((TypeError, ValueError)):
        RiskConfiguration(maximum_order_quantity=value)
    with pytest.raises((TypeError, ValueError)):
        RiskConfiguration(maximum_position_quantity=value)


@pytest.mark.parametrize(
    "value", [Decimal("0"), Decimal("-1"), Decimal("Infinity"), 100.0]
)
def test_notional_limit_must_be_positive_finite_decimal(value) -> None:
    with pytest.raises((TypeError, ValueError)):
        RiskConfiguration(maximum_order_notional=value)


def test_order_quantity_limit_is_inclusive() -> None:
    approved = evaluate(RiskConfiguration(maximum_order_quantity=2))
    rejected = evaluate(RiskConfiguration(maximum_order_quantity=1))
    assert approved.status is RiskDecisionStatus.APPROVED
    assert rejected.reason is RiskRejectionReason.ORDER_QUANTITY_LIMIT_EXCEEDED


def test_resulting_position_uses_buy_addition_and_sell_subtraction() -> None:
    portfolio = PortfolioState(Decimal("1000"))
    portfolio.apply_fill(
        Fill(NVDA, OrderSide.BUY, 3, CREATED_AT, Decimal("10"), Decimal("0"))
    )
    buy = evaluate(
        RiskConfiguration(maximum_position_quantity=4),
        order=request(OrderSide.BUY, 2),
        portfolio=portfolio,
    )
    sell = evaluate(
        RiskConfiguration(maximum_position_quantity=2),
        order=request(OrderSide.SELL, 1),
        portfolio=portfolio,
    )
    assert buy.reason is RiskRejectionReason.POSITION_QUANTITY_LIMIT_EXCEEDED
    assert sell.status is RiskDecisionStatus.APPROVED


def test_sell_beyond_position_is_risk_rejected_before_execution() -> None:
    decision = evaluate(
        RiskConfiguration(),
        order=request(OrderSide.SELL, 1),
    )
    assert decision.reason is RiskRejectionReason.SHORT_POSITION_NOT_ALLOWED


def test_equity_order_notional_uses_explicit_decimal_price_and_inclusive_limit() -> None:
    approved = evaluate(
        RiskConfiguration(maximum_order_notional=Decimal("200")),
        context=valuation(Decimal("100.0")),
    )
    rejected = evaluate(
        RiskConfiguration(maximum_order_notional=Decimal("199.99")),
        context=valuation(Decimal("100.0")),
    )
    assert approved.status is RiskDecisionStatus.APPROVED
    assert (
        rejected.reason
        is RiskRejectionReason.ORDER_NOTIONAL_LIMIT_EXCEEDED
    )


def test_price_is_not_required_when_no_valuation_rule_is_enabled() -> None:
    decision = evaluate(
        RiskConfiguration(maximum_order_quantity=2),
        context=valuation(None),
    )
    assert decision.status is RiskDecisionStatus.APPROVED


def test_notional_rule_fails_closed_for_missing_or_invalid_price() -> None:
    configuration = RiskConfiguration(maximum_order_notional=Decimal("1000"))
    missing = evaluate(configuration, context=valuation(None))
    invalid = evaluate(configuration, context=valuation(Decimal("NaN")))
    assert missing.reason is RiskRejectionReason.MISSING_MARKET_PRICE
    assert invalid.reason is RiskRejectionReason.INVALID_MARKET_PRICE


def test_first_rejection_follows_deterministic_rule_order() -> None:
    decision = evaluate(
        RiskConfiguration(
            allowed_instruments=frozenset(),
            maximum_order_quantity=1,
            maximum_order_notional=Decimal("1"),
        )
    )
    assert decision.reason is RiskRejectionReason.INSTRUMENT_NOT_ALLOWED


def test_evaluation_is_deterministic_and_uses_valuation_observed_at() -> None:
    configuration = RiskConfiguration(maximum_order_notional=Decimal("1000"))
    first = evaluate(configuration)
    second = evaluate(configuration)
    assert first == second
    assert first.evaluated_at == EVALUATED_AT


def test_approval_and_rejection_do_not_mutate_portfolio_or_create_fill() -> None:
    portfolio = PortfolioState(Decimal("1000"))
    before = (portfolio.cash, dict(portfolio.quantities))
    approved = evaluate(RiskConfiguration(), portfolio=portfolio)
    rejected = evaluate(
        RiskConfiguration(maximum_order_quantity=1), portfolio=portfolio
    )
    assert (portfolio.cash, dict(portfolio.quantities)) == before
    assert approved.request == request()
    assert rejected.request == request()
    assert not isinstance(approved, Fill)
    assert not isinstance(rejected, Fill)
