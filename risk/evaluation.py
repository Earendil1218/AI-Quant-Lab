"""Deterministic fail-closed pre-trade risk orchestration."""

from __future__ import annotations

from portfolio.state import PortfolioState
from risk.models import (
    RiskConfiguration,
    RiskDecision,
    RiskDecisionStatus,
    RiskRejectionReason,
    ValuationContext,
)
from risk.rules import equity_order_notional, resulting_position_quantity
from trading.instruments import AssetClass
from trading.orders import OrderRequest


def _decision(
    request: OrderRequest,
    valuation: ValuationContext,
    reason: RiskRejectionReason | None = None,
) -> RiskDecision:
    status = (
        RiskDecisionStatus.APPROVED
        if reason is None
        else RiskDecisionStatus.REJECTED
    )
    return RiskDecision(status, request, valuation.observed_at, reason)


def evaluate_order_risk(
    request: OrderRequest,
    portfolio: PortfolioState,
    valuation: ValuationContext,
    configuration: RiskConfiguration,
) -> RiskDecision:
    """Evaluate one order without state mutation. / 评估单个订单且不修改状态。"""
    if not isinstance(request, OrderRequest):
        raise TypeError("request must be an OrderRequest.")
    if not isinstance(portfolio, PortfolioState):
        raise TypeError("portfolio must be a PortfolioState.")
    if not isinstance(valuation, ValuationContext):
        raise TypeError("valuation must be a ValuationContext.")
    if not isinstance(configuration, RiskConfiguration):
        raise TypeError("configuration must be a RiskConfiguration.")

    allowed = configuration.allowed_instruments
    if allowed is not None and request.instrument not in allowed:
        return _decision(
            request, valuation, RiskRejectionReason.INSTRUMENT_NOT_ALLOWED
        )

    order_limit = configuration.maximum_order_quantity
    if order_limit is not None and request.quantity > order_limit:
        return _decision(
            request,
            valuation,
            RiskRejectionReason.ORDER_QUANTITY_LIMIT_EXCEEDED,
        )

    resulting_quantity = resulting_position_quantity(request, portfolio)
    if resulting_quantity < 0:
        return _decision(
            request, valuation, RiskRejectionReason.SHORT_POSITION_NOT_ALLOWED
        )

    position_limit = configuration.maximum_position_quantity
    if position_limit is not None and resulting_quantity > position_limit:
        return _decision(
            request,
            valuation,
            RiskRejectionReason.POSITION_QUANTITY_LIMIT_EXCEEDED,
        )

    notional_limit = configuration.maximum_order_notional
    if notional_limit is not None:
        if request.instrument.asset_class is not AssetClass.EQUITY:
            return _decision(
                request,
                valuation,
                RiskRejectionReason.UNSUPPORTED_ASSET_CLASS,
            )
        if request.instrument not in valuation.prices:
            return _decision(
                request, valuation, RiskRejectionReason.MISSING_MARKET_PRICE
            )
        price = valuation.prices[request.instrument]
        if not price.is_finite() or price <= 0:
            return _decision(
                request, valuation, RiskRejectionReason.INVALID_MARKET_PRICE
            )
        if equity_order_notional(request, price) > notional_limit:
            return _decision(
                request,
                valuation,
                RiskRejectionReason.ORDER_NOTIONAL_LIMIT_EXCEEDED,
            )

    return _decision(request, valuation)
