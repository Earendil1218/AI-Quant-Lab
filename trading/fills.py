"""Execution outcomes shared by simulation and future broker adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from trading.instruments import InstrumentId
from trading.orders import OrderRequest, OrderSide


def _require_decimal(name: str, value: Decimal, *, positive: bool = False) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal.")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite.")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive.")
    if not positive and value < 0:
        raise ValueError(f"{name} must not be negative.")


@dataclass(frozen=True)
class Fill:
    instrument: InstrumentId
    side: OrderSide
    quantity: int
    filled_at: datetime
    price: Decimal
    commission: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, InstrumentId):
            raise TypeError("instrument must be an InstrumentId.")
        if not isinstance(self.side, OrderSide):
            raise TypeError("side must be an OrderSide.")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise TypeError("quantity must be an integer (bool is not accepted).")
        if self.quantity <= 0:
            raise ValueError("fill quantity must be positive.")
        if not isinstance(self.filled_at, datetime):
            raise TypeError("filled_at must be a datetime.")
        _require_decimal("price", self.price, positive=True)
        _require_decimal("commission", self.commission)


class ExecutionRejectionReason(str, Enum):
    """Execution-horizon failures, separate from planning decisions."""

    INSUFFICIENT_CASH = "insufficient_cash"
    NO_NEXT_BAR = "no_next_bar"


@dataclass(frozen=True)
class ExecutionRejection:
    request: OrderRequest
    reason: ExecutionRejectionReason
    rejected_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.request, OrderRequest):
            raise TypeError("request must be an OrderRequest.")
        if not isinstance(self.reason, ExecutionRejectionReason):
            raise TypeError("reason must be an ExecutionRejectionReason.")
        if not isinstance(self.rejected_at, datetime):
            raise TypeError("rejected_at must be a datetime.")
