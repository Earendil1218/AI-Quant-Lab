"""Reconcile sized targets with current portfolio positions."""

from __future__ import annotations

from portfolio.sizing import SizingPolicy
from portfolio.state import PortfolioState
from trading.intents import TargetExposureIntent
from trading.orders import (
    OrderPlan,
    OrderRequest,
    OrderSide,
    PlanningDecision,
)


def plan_target_order(
    intent: TargetExposureIntent,
    sizing_policy: SizingPolicy,
    portfolio: PortfolioState,
) -> OrderPlan:
    """Plan at most one long/flat order without assessing execution feasibility."""
    if not isinstance(intent, TargetExposureIntent):
        raise TypeError("intent must be a TargetExposureIntent.")
    if not isinstance(portfolio, PortfolioState):
        raise TypeError("portfolio must be a PortfolioState.")
    target = sizing_policy.size(intent)
    if target is None:
        return OrderPlan(PlanningDecision.INTENT_UNAVAILABLE)
    current = portfolio.quantity_for(target.instrument)
    difference = target.quantity - current
    if difference == 0:
        return OrderPlan(PlanningDecision.TARGET_ALREADY_SATISFIED)
    side = OrderSide.BUY if difference > 0 else OrderSide.SELL
    request = OrderRequest(
        instrument=target.instrument,
        side=side,
        quantity=abs(difference),
        created_at=target.observed_at,
    )
    return OrderPlan(PlanningDecision.ORDER_REQUIRED, request)
