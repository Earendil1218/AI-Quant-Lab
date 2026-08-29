"""Strategy DataFrame to trading-domain adapter tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest import adapt_latest_strategy_intent
from trading import AssetClass, InstrumentId


NVDA = InstrumentId(AssetClass.EQUITY, "NVDA")


def intent_frame(targets: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_type": ["moving_average_crossover"] * len(targets),
            "signal_state": ["unavailable" if np.isnan(value) else "above" for value in targets],
            "target_position": targets,
        },
        index=pd.date_range("2026-01-01", periods=len(targets), freq="D", name="date"),
    )


def test_adapter_adds_instrument_and_maps_warmup_to_none() -> None:
    actual = adapt_latest_strategy_intent(intent_frame([np.nan]), NVDA)
    assert actual.instrument == NVDA
    assert actual.target_exposure is None
    assert actual.observed_at.date().isoformat() == "2026-01-01"


def test_adapter_uses_latest_row_and_preserves_signal_metadata() -> None:
    actual = adapt_latest_strategy_intent(intent_frame([np.nan, 1.0]), NVDA)
    assert actual.target_exposure == 1.0
    assert actual.signal_type == "moving_average_crossover"
    assert actual.signal_state == "above"


def test_adapter_does_not_mutate_input() -> None:
    frame = intent_frame([np.nan, 1.0])
    original = frame.copy(deep=True)
    adapt_latest_strategy_intent(frame, NVDA)
    pd.testing.assert_frame_equal(frame, original)


def test_adapter_rejects_invalid_contracts() -> None:
    frame = intent_frame([1.0])
    with pytest.raises(TypeError, match="DataFrame"):
        adapt_latest_strategy_intent([], NVDA)
    with pytest.raises(ValueError, match="missing"):
        adapt_latest_strategy_intent(frame.drop(columns="signal_state"), NVDA)
    with pytest.raises(TypeError, match="DatetimeIndex"):
        adapt_latest_strategy_intent(frame.reset_index(drop=True), NVDA)
    aware = frame.copy()
    aware.index = aware.index.tz_localize("UTC")
    with pytest.raises(ValueError, match="timezone-naive"):
        adapt_latest_strategy_intent(aware, NVDA)
