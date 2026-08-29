"""Stable strategy contracts, independent of brokers and execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

import pandas as pd


class SignalState(str, Enum):
    """Observable market state; warm-up is explicitly unavailable."""

    UNAVAILABLE = "unavailable"
    ABOVE = "above"
    BELOW_OR_EQUAL = "below_or_equal"


class Strategy(ABC):
    """A deterministic transformation from market data to target exposure."""

    @abstractmethod
    def generate_intents(self, market_data: pd.DataFrame) -> pd.DataFrame:
        """Return date-indexed strategy intent without placing orders."""
