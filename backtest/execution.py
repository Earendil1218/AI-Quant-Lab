"""Deterministic next-open simulated execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from portfolio.state import PortfolioState
from trading.fills import ExecutionRejection, ExecutionRejectionReason, Fill
from trading.orders import OrderRequest, OrderSide


def _validate_non_negative_decimal(name: str, value: Decimal) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal.")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be finite and non-negative.")


@dataclass(frozen=True)
class ExecutionCosts:
    """Simple deterministic costs; precision begins at execution/accounting."""

    fixed_commission: Decimal = Decimal("0")
    slippage_bps: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        _validate_non_negative_decimal("fixed_commission", self.fixed_commission)
        _validate_non_negative_decimal("slippage_bps", self.slippage_bps)
        if self.slippage_bps >= Decimal("10000"):
            raise ValueError("slippage_bps must be less than 10000.")


def simulate_next_open_execution(
    request: OrderRequest,
    *,
    open_price: float,
    filled_at: datetime,
    portfolio: PortfolioState,
    costs: ExecutionCosts,
) -> Fill | ExecutionRejection:
    """Fill a pending order at the next open, subject to available cash."""
    if not isinstance(request, OrderRequest):
        raise TypeError("request must be an OrderRequest.")
    if not isinstance(portfolio, PortfolioState):
        raise TypeError("portfolio must be a PortfolioState.")
    if not isinstance(costs, ExecutionCosts):
        raise TypeError("costs must be ExecutionCosts.")
    if isinstance(open_price, bool) or not isinstance(open_price, (int, float)):
        raise TypeError("open_price must be numeric.")
    base_price = Decimal(str(open_price))
    if not base_price.is_finite() or base_price <= 0:
        raise ValueError("open_price must be finite and positive.")
    slippage_rate = costs.slippage_bps / Decimal("10000")
    if request.side is OrderSide.BUY:
        fill_price = base_price * (Decimal("1") + slippage_rate)
        resulting_cash = (
            portfolio.cash
            - fill_price * request.quantity
            - costs.fixed_commission
        )
    else:
        if request.quantity > portfolio.quantity_for(request.instrument):
            raise ValueError("sell request would exceed the current long position.")
        fill_price = base_price * (Decimal("1") - slippage_rate)
        if fill_price <= 0:
            raise ValueError("slippage produces a non-positive sell fill price.")
        resulting_cash = (
            portfolio.cash
            + fill_price * request.quantity
            - costs.fixed_commission
        )
    if resulting_cash < 0:
        return ExecutionRejection(
            request,
            ExecutionRejectionReason.INSUFFICIENT_CASH,
            filled_at,
        )
    return Fill(
        instrument=request.instrument,
        side=request.side,
        quantity=request.quantity,
        filled_at=filled_at,
        price=fill_price,
        commission=costs.fixed_commission,
    )
