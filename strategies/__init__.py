"""Pure signal generation and strategy-intent public API."""

from strategies.base import SignalState, Strategy
from strategies.moving_average import (
    MovingAverageCrossoverStrategy,
    generate_moving_average_crossover_signals,
)

__all__ = [
    "generate_moving_average_crossover_signals",
    "MovingAverageCrossoverStrategy",
    "SignalState",
    "Strategy",
]
