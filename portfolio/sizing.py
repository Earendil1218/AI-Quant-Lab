"""Sizing policies transform strategy exposure into target quantity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from trading.intents import TargetExposureIntent, TargetQuantity


class SizingPolicy(Protocol):
    """Boundary between strategy state and tradable quantity."""

    def size(self, intent: TargetExposureIntent) -> TargetQuantity | None:
        """Return a target quantity, or None for an unavailable intent."""


@dataclass(frozen=True)
class FixedQuantitySizing:
    """Map Phase 3E long/flat exposure to a configured equity quantity."""

    long_quantity: int

    def __post_init__(self) -> None:
        if isinstance(self.long_quantity, bool) or not isinstance(
            self.long_quantity, int
        ):
            raise TypeError("long_quantity must be an integer (bool is not accepted).")
        if self.long_quantity <= 0:
            raise ValueError("long_quantity must be positive.")

    def size(self, intent: TargetExposureIntent) -> TargetQuantity | None:
        if not isinstance(intent, TargetExposureIntent):
            raise TypeError("intent must be a TargetExposureIntent.")
        if intent.target_exposure is None:
            return None
        quantity = self.long_quantity if intent.target_exposure == 1.0 else 0
        return TargetQuantity(intent.instrument, intent.observed_at, quantity)
