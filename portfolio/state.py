"""Precise portfolio accounting driven only by fills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from trading.fills import Fill
from trading.instruments import InstrumentId
from trading.orders import OrderSide


def _validate_money(name: str, value: Decimal, *, positive: bool = False) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal.")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite.")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive.")
    if not positive and value < 0:
        raise ValueError(f"{name} must not be negative.")


@dataclass(frozen=True)
class Position:
    instrument: InstrumentId
    quantity: int

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, InstrumentId):
            raise TypeError("instrument must be an InstrumentId.")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise TypeError("quantity must be an integer (bool is not accepted).")
        if self.quantity < 0:
            raise ValueError("position quantity must not be negative.")


@dataclass(frozen=True)
class PortfolioSnapshot:
    observed_at: datetime
    cash: Decimal
    positions: tuple[Position, ...]
    market_value: Decimal
    equity: Decimal


class PortfolioState:
    """Mutable simulation state; external views are immutable snapshots."""

    def __init__(self, initial_cash: Decimal) -> None:
        _validate_money("initial_cash", initial_cash)
        self._cash = initial_cash
        self._quantities: dict[InstrumentId, int] = {}

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def quantities(self) -> Mapping[InstrumentId, int]:
        return MappingProxyType(self._quantities)

    def quantity_for(self, instrument: InstrumentId) -> int:
        if not isinstance(instrument, InstrumentId):
            raise TypeError("instrument must be an InstrumentId.")
        return self._quantities.get(instrument, 0)

    def apply_fill(self, fill: Fill) -> None:
        """Apply a completed fill; order requests never mutate portfolio state."""
        if not isinstance(fill, Fill):
            raise TypeError("fill must be a Fill.")
        gross = fill.price * fill.quantity
        current = self.quantity_for(fill.instrument)
        if fill.side is OrderSide.BUY:
            cash_after = self._cash - gross - fill.commission
            quantity_after = current + fill.quantity
        else:
            quantity_after = current - fill.quantity
            if quantity_after < 0:
                raise ValueError("sell fill would create a short position.")
            cash_after = self._cash + gross - fill.commission
        if cash_after < 0:
            raise ValueError("fill would create negative cash.")
        self._cash = cash_after
        if quantity_after:
            self._quantities[fill.instrument] = quantity_after
        else:
            self._quantities.pop(fill.instrument, None)

    def snapshot(
        self,
        observed_at: datetime,
        marks: Mapping[InstrumentId, Decimal],
    ) -> PortfolioSnapshot:
        if not isinstance(observed_at, datetime):
            raise TypeError("observed_at must be a datetime.")
        market_value = Decimal("0")
        positions: list[Position] = []
        for instrument, quantity in sorted(
            self._quantities.items(),
            key=lambda item: (item[0].asset_class.value, item[0].symbol),
        ):
            if instrument not in marks:
                raise ValueError(f"Missing mark for {instrument.symbol}.")
            mark = marks[instrument]
            _validate_money("mark", mark, positive=True)
            market_value += mark * quantity
            positions.append(Position(instrument, quantity))
        return PortfolioSnapshot(
            observed_at=observed_at,
            cash=self._cash,
            positions=tuple(positions),
            market_value=market_value,
            equity=self._cash + market_value,
        )
