"""Signal and strategy-intent financial semantics."""

from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from strategies import (
    MovingAverageCrossoverStrategy,
    SignalState,
    Strategy,
    generate_moving_average_crossover_signals,
)


def market_data(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [100.0] * len(closes),
        }
    )


def test_signal_contains_identity_state_and_numeric_value() -> None:
    actual = generate_moving_average_crossover_signals(
        market_data([1, 2, 3, 2, 1]), 2, 3
    )
    assert actual.columns.tolist() == [
        "signal_type",
        "fast_moving_average",
        "slow_moving_average",
        "signal_state",
        "signal_value",
    ]
    assert actual["signal_type"].eq("moving_average_crossover").all()
    assert actual.index.name == "date"
    assert actual["signal_state"].tolist() == [
        "unavailable",
        "unavailable",
        "above",
        "above",
        "below_or_equal",
    ]
    assert actual.loc[pd.Timestamp("2026-01-05"), "signal_value"] < 0


def test_equal_averages_are_flat_not_long() -> None:
    actual = generate_moving_average_crossover_signals(market_data([2, 2, 2]), 2, 3)
    assert actual.iloc[-1]["signal_state"] == SignalState.BELOW_OR_EQUAL.value


def test_warmup_intent_is_nan_then_long_or_flat() -> None:
    strategy = MovingAverageCrossoverStrategy(2, 3)
    actual = strategy.generate_intents(market_data([1, 2, 3, 2, 1]))
    assert actual.columns.tolist() == [
        "signal_type",
        "signal_state",
        "target_position",
    ]
    assert actual["target_position"].iloc[:2].isna().all()
    assert actual["target_position"].iloc[2:].tolist() == [1.0, 1.0, 0.0]
    assert actual["target_position"].dtype == "float64"


def test_reference_strategy_satisfies_public_abstraction() -> None:
    assert isinstance(MovingAverageCrossoverStrategy(2, 3), Strategy)


@pytest.mark.parametrize(
    "fast,slow,error,message",
    [
        (0, 3, ValueError, "positive"),
        (2, -1, ValueError, "positive"),
        (3, 3, ValueError, "less"),
        (4, 3, ValueError, "less"),
        (True, 3, TypeError, "integer"),
        (1, False, TypeError, "integer"),
        (1.0, 3, TypeError, "integer"),
    ],
)
def test_strategy_rejects_invalid_windows(fast, slow, error, message) -> None:
    with pytest.raises(error, match=message):
        MovingAverageCrossoverStrategy(fast, slow)


def test_strategy_is_deterministic_and_does_not_mutate_input() -> None:
    frame = market_data([1, 2, 3, 2, 1])
    original = frame.copy(deep=True)
    strategy = MovingAverageCrossoverStrategy(2, 3)
    first = strategy.generate_intents(frame)
    second = strategy.generate_intents(frame)
    assert_frame_equal(first, second)
    assert_frame_equal(frame, original)


def test_future_price_mutation_cannot_change_historical_results() -> None:
    frame = market_data([1, 2, 3, 4, 5, 6])
    changed_future = frame.copy(deep=True)
    changed_future.loc[4:, ["open", "high", "low", "close"]] = 1000.0
    strategy = MovingAverageCrossoverStrategy(2, 3)

    original = strategy.generate_intents(frame)
    mutated = strategy.generate_intents(changed_future)

    assert_frame_equal(original.iloc[:4], mutated.iloc[:4])


def test_appending_future_observations_cannot_change_history() -> None:
    short = market_data([1, 2, 3, 4])
    long = market_data([1, 2, 3, 4, 100, 1])
    strategy = MovingAverageCrossoverStrategy(2, 3)
    assert_frame_equal(
        strategy.generate_intents(short),
        strategy.generate_intents(long).iloc[:4],
    )
