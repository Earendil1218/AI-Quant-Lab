"""Broker-neutral pre-trade risk records. / 与 broker 无关的交易前风险记录。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from trading.instruments import InstrumentId
from trading.orders import OrderRequest


def _validate_positive_limit(name: str, value: int | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            f"{name} must be an integer or None (bool is not accepted)."
        )
    if value <= 0:
        raise ValueError(f"{name} must be positive when enabled.")


@dataclass(frozen=True)
class RiskConfiguration:
    """Enable only explicitly configured pre-trade limits. / 仅启用显式配置的交易前限制。"""

    allowed_instruments: frozenset[InstrumentId] | None = None
    maximum_order_quantity: int | None = None
    maximum_position_quantity: int | None = None
    maximum_order_notional: Decimal | None = None

    def __post_init__(self) -> None:
        if self.allowed_instruments is not None:
            if not isinstance(self.allowed_instruments, frozenset):
                raise TypeError("allowed_instruments must be a frozenset or None.")
            if any(
                not isinstance(instrument, InstrumentId)
                for instrument in self.allowed_instruments
            ):
                raise TypeError("allowed_instruments must contain only InstrumentId values.")
        _validate_positive_limit(
            "maximum_order_quantity", self.maximum_order_quantity
        )
        _validate_positive_limit(
            "maximum_position_quantity", self.maximum_position_quantity
        )
        if self.maximum_order_notional is not None:
            value = self.maximum_order_notional
            if not isinstance(value, Decimal):
                raise TypeError("maximum_order_notional must be a Decimal or None.")
            if not value.is_finite() or value <= 0:
                raise ValueError(
                    "maximum_order_notional must be finite and positive when enabled."
                )


@dataclass(frozen=True)
class ValuationContext:
    """Observed prices for one deterministic risk horizon. / 单一确定性风控时点的观察价格。"""

    observed_at: datetime
    prices: Mapping[InstrumentId, Decimal]

    def __post_init__(self) -> None:
        if not isinstance(self.observed_at, datetime):
            raise TypeError("observed_at must be a datetime.")
        if not isinstance(self.prices, Mapping):
            raise TypeError("prices must be a mapping.")
        copied: dict[InstrumentId, Decimal] = {}
        for instrument, price in self.prices.items():
            if not isinstance(instrument, InstrumentId):
                raise TypeError("price keys must be InstrumentId values.")
            if not isinstance(price, Decimal):
                raise TypeError("prices must be Decimal values.")
            copied[instrument] = price
        object.__setattr__(self, "prices", MappingProxyType(copied))


class RiskDecisionStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class RiskRejectionReason(str, Enum):
    INSTRUMENT_NOT_ALLOWED = "instrument_not_allowed"
    ORDER_QUANTITY_LIMIT_EXCEEDED = "order_quantity_limit_exceeded"
    SHORT_POSITION_NOT_ALLOWED = "short_position_not_allowed"
    POSITION_QUANTITY_LIMIT_EXCEEDED = "position_quantity_limit_exceeded"
    UNSUPPORTED_ASSET_CLASS = "unsupported_asset_class"
    MISSING_MARKET_PRICE = "missing_market_price"
    INVALID_MARKET_PRICE = "invalid_market_price"
    ORDER_NOTIONAL_LIMIT_EXCEEDED = "order_notional_limit_exceeded"


@dataclass(frozen=True)
class RiskDecision:
    """A risk result that grants no execution authority. / 不授予执行权限的风险结果。"""

    status: RiskDecisionStatus
    request: OrderRequest
    evaluated_at: datetime
    reason: RiskRejectionReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, RiskDecisionStatus):
            raise TypeError("status must be a RiskDecisionStatus.")
        if not isinstance(self.request, OrderRequest):
            raise TypeError("request must be an OrderRequest.")
        if not isinstance(self.evaluated_at, datetime):
            raise TypeError("evaluated_at must be a datetime.")
        if self.reason is not None and not isinstance(
            self.reason, RiskRejectionReason
        ):
            raise TypeError("reason must be a RiskRejectionReason or None.")
        rejected = self.status is RiskDecisionStatus.REJECTED
        if rejected != (self.reason is not None):
            raise ValueError(
                "Rejected decisions require a reason; approvals cannot have one."
            )
