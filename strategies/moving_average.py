"""Moving-average crossover signal and reference strategy."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from research.indicators import calculate_moving_average
from strategies.base import SignalState, Strategy


def _validate_windows(fast_window: int, slow_window: int) -> None:
    for name, window in (("fast_window", fast_window), ("slow_window", slow_window)):
        if isinstance(window, bool) or not isinstance(window, int):
            raise TypeError(f"{name} must be an integer (bool is not accepted).")
        if window <= 0:
            raise ValueError(f"{name} must be positive.")
    if fast_window >= slow_window:
        raise ValueError("fast_window must be less than slow_window.")


def generate_moving_average_crossover_signals(
    market_data: pd.DataFrame,
    fast_window: int,
    slow_window: int,
) -> pd.DataFrame:
    """Describe whether the trailing fast MA is above the trailing slow MA."""
    _validate_windows(fast_window, slow_window)
    fast = calculate_moving_average(market_data, fast_window)
    slow = calculate_moving_average(market_data, slow_window)
    available = fast.notna() & slow.notna()
    states = pd.Series(
        SignalState.UNAVAILABLE.value,
        index=fast.index,
        name="signal_state",
        dtype="string",
    )
    states.loc[available & (fast > slow)] = SignalState.ABOVE.value
    states.loc[available & (fast <= slow)] = SignalState.BELOW_OR_EQUAL.value

    return pd.DataFrame(
        {
            "signal_type": pd.Series(
                "moving_average_crossover",
                index=fast.index,
                dtype="string",
            ),
            "fast_moving_average": fast,
            "slow_moving_average": slow,
            "signal_state": states,
            "signal_value": (fast - slow).astype("float64"),
        },
        index=fast.index,
    )


@dataclass(frozen=True)
class MovingAverageCrossoverStrategy(Strategy):
    """Reference long/flat strategy based on a trailing MA state."""

    fast_window: int
    slow_window: int

    def __post_init__(self) -> None:
        _validate_windows(self.fast_window, self.slow_window)

    def generate_signals(self, market_data: pd.DataFrame) -> pd.DataFrame:
        return generate_moving_average_crossover_signals(
            market_data,
            self.fast_window,
            self.slow_window,
        )

    def generate_intents(self, market_data: pd.DataFrame) -> pd.DataFrame:
        signals = self.generate_signals(market_data)
        target = pd.Series(np.nan, index=signals.index, dtype="float64")
        target.loc[signals["signal_state"] == SignalState.ABOVE.value] = 1.0
        target.loc[
            signals["signal_state"] == SignalState.BELOW_OR_EQUAL.value
        ] = 0.0
        return pd.DataFrame(
            {
                "signal_type": signals["signal_type"],
                "signal_state": signals["signal_state"],
                "target_position": target,
            },
            index=signals.index,
        )
