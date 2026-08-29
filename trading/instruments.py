"""Broker-neutral instrument identity. / 与 broker 无关的标的身份。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AssetClass(str, Enum):
    """Asset classes currently supported by the trading domain."""

    EQUITY = "equity"


@dataclass(frozen=True)
class InstrumentId:
    """Stable identity shared by strategy adapters, portfolios, and execution."""

    asset_class: AssetClass
    symbol: str

    def __post_init__(self) -> None:
        if not isinstance(self.asset_class, AssetClass):
            raise TypeError("asset_class must be an AssetClass.")
        if not isinstance(self.symbol, str):
            raise TypeError("symbol must be a string.")
        normalized = self.symbol.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty.")
        object.__setattr__(self, "symbol", normalized)
