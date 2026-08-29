"""Strategy intent and sized target contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from trading.instruments import InstrumentId


@dataclass(frozen=True)
class TargetExposureIntent:
    """Desired strategy state; exposure is deliberately not a share quantity."""

    instrument: InstrumentId
    observed_at: datetime
    target_exposure: float | None
    signal_type: str
    signal_state: str

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, InstrumentId):
            raise TypeError("instrument must be an InstrumentId.")
        if not isinstance(self.observed_at, datetime):
            raise TypeError("observed_at must be a datetime.")
        if self.target_exposure is not None:
            if isinstance(self.target_exposure, bool) or not isinstance(
                self.target_exposure, (int, float)
            ):
                raise TypeError("target_exposure must be a number or None.")
            exposure = float(self.target_exposure)
            if not isfinite(exposure):
                raise ValueError("target_exposure must be finite when available.")
            if exposure not in (0.0, 1.0):
                raise ValueError("Phase 3E target_exposure must be 0.0 or 1.0.")
            object.__setattr__(self, "target_exposure", exposure)
        for name, value in (
            ("signal_type", self.signal_type),
            ("signal_state", self.signal_state),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")


@dataclass(frozen=True)
class TargetQuantity:
    """A sizing-policy output, separate from strategy target exposure."""

    instrument: InstrumentId
    observed_at: datetime
    quantity: int

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, InstrumentId):
            raise TypeError("instrument must be an InstrumentId.")
        if not isinstance(self.observed_at, datetime):
            raise TypeError("observed_at must be a datetime.")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise TypeError("quantity must be an integer (bool is not accepted).")
        if self.quantity < 0:
            raise ValueError("quantity must not be negative.")
