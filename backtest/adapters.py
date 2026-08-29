"""Adapters between pandas strategy output and the trading domain."""

from __future__ import annotations

import pandas as pd

from trading.instruments import InstrumentId
from trading.intents import TargetExposureIntent


def adapt_latest_strategy_intent(
    intents: pd.DataFrame,
    instrument: InstrumentId,
) -> TargetExposureIntent:
    """Convert the latest Phase 3D output row into a typed domain intent."""
    required = ("signal_type", "signal_state", "target_position")
    if not isinstance(intents, pd.DataFrame):
        raise TypeError("Strategy intents must be a pandas DataFrame.")
    if not isinstance(instrument, InstrumentId):
        raise TypeError("instrument must be an InstrumentId.")
    if intents.empty:
        raise ValueError("Strategy intents must not be empty.")
    missing = [column for column in required if column not in intents.columns]
    if missing:
        raise ValueError(f"Strategy intents missing columns: {', '.join(missing)}")
    if not isinstance(intents.index, pd.DatetimeIndex):
        raise TypeError("Strategy intent index must be a DatetimeIndex.")
    if intents.index.tz is not None:
        raise ValueError("Strategy intent dates must be timezone-naive.")
    if intents.index.has_duplicates or not intents.index.is_monotonic_increasing:
        raise ValueError("Strategy intent dates must be unique and ascending.")
    row = intents.iloc[-1]
    raw_target = row["target_position"]
    target = None if pd.isna(raw_target) else float(raw_target)
    return TargetExposureIntent(
        instrument=instrument,
        observed_at=pd.Timestamp(intents.index[-1]).to_pydatetime(),
        target_exposure=target,
        signal_type=str(row["signal_type"]),
        signal_state=str(row["signal_state"]),
    )
