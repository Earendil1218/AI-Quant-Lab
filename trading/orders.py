"""Broker-neutral order planning contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from trading.instruments import InstrumentId


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class OrderRequest:
    """An execution request with no broker-specific fields."""

    instrument: InstrumentId
    side: OrderSide
    quantity: int
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, InstrumentId):
            raise TypeError("instrument must be an InstrumentId.")
        if not isinstance(self.side, OrderSide):
            raise TypeError("side must be an OrderSide.")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise TypeError("quantity must be an integer (bool is not accepted).")
        if self.quantity <= 0:
            raise ValueError("order quantity must be positive.")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime.")


class PlanningDecision(str, Enum):
    """Target-reconciliation outcomes; not execution rejection states."""

    ORDER_REQUIRED = "order_required"
    TARGET_ALREADY_SATISFIED = "target_already_satisfied"
    INTENT_UNAVAILABLE = "intent_unavailable"


@dataclass(frozen=True)
class OrderPlan:
    decision: PlanningDecision
    request: OrderRequest | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, PlanningDecision):
            raise TypeError("decision must be a PlanningDecision.")
        requires_order = self.decision is PlanningDecision.ORDER_REQUIRED
        if requires_order != (self.request is not None):
            raise ValueError("Only ORDER_REQUIRED plans may contain an order request.")
