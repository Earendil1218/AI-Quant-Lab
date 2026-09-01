"""Pure calculations used by pre-trade risk evaluation."""

from __future__ import annotations

from decimal import Decimal

from portfolio.state import PortfolioState
from trading.orders import OrderRequest, OrderSide


def resulting_position_quantity(
    request: OrderRequest,
    portfolio: PortfolioState,
) -> int:
    """Return post-order quantity without mutating the portfolio."""
    current = portfolio.quantity_for(request.instrument)
    if request.side is OrderSide.BUY:
        return current + request.quantity
    return current - request.quantity


def equity_order_notional(request: OrderRequest, price: Decimal) -> Decimal:
    """Return unsigned equity order notional at an explicit observed price."""
    return price * request.quantity
