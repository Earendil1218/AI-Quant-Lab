"""股票价格收益率的确定性离线测试。Deterministic stock-return tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_series_equal

from research.returns import (
    calculate_cumulative_returns,
    calculate_log_returns,
    calculate_simple_returns,
)


def price_history(prices: list[object] | None = None) -> pd.DataFrame:
    closes = [100.0, 110.0, 121.0] if prices is None else prices
    dates = pd.date_range("2026-08-17", periods=len(closes), freq="D")
    numeric = pd.to_numeric(pd.Series(closes), errors="coerce")
    return pd.DataFrame(
        {
            "date": dates,
            "open": numeric,
            "high": numeric,
            "low": numeric,
            "close": closes,
            "volume": [1000.0] * len(closes),
        }
    )


def test_calculates_simple_returns_and_preserves_leading_nan() -> None:
    actual = calculate_simple_returns(price_history())
    expected = pd.Series([np.nan, 0.1, 0.1], name="simple_return")

    assert_series_equal(actual, expected)


def test_calculates_log_returns() -> None:
    actual = calculate_log_returns(price_history())
    expected = pd.Series(
        [np.nan, np.log(110 / 100), np.log(121 / 110)],
        name="log_return",
    )

    assert_series_equal(actual, expected)


def test_compounds_simple_returns_instead_of_summing() -> None:
    simple = calculate_simple_returns(price_history())

    actual = calculate_cumulative_returns(simple)

    assert actual.name == "cumulative_return"
    assert np.isnan(actual.iloc[0])
    assert actual.iloc[-1] == pytest.approx(0.21)


def test_return_calculation_does_not_mutate_input() -> None:
    frame = price_history()
    original = frame.copy(deep=True)

    calculate_simple_returns(frame)
    calculate_log_returns(frame)

    pd.testing.assert_frame_equal(frame, original)


def test_single_row_preserves_one_nan_observation() -> None:
    actual = calculate_simple_returns(price_history([100.0]))

    assert len(actual) == 1
    assert actual.dtype == "float64"
    assert actual.isna().all()


def test_research_layer_rejects_zero_close() -> None:
    with pytest.raises(ValueError, match="strictly positive"):
        calculate_simple_returns(price_history([100.0, 0.0]))


def test_reuses_validation_to_reject_negative_close() -> None:
    with pytest.raises(ValueError, match="不得为负值"):
        calculate_simple_returns(price_history([100.0, -1.0]))


def test_reuses_processed_contract_for_empty_or_invalid_frames() -> None:
    with pytest.raises(ValueError):
        calculate_simple_returns(pd.DataFrame())

    with pytest.raises(ValueError, match="close"):
        calculate_simple_returns(price_history().drop(columns="close"))


@pytest.mark.parametrize(
    "values",
    [
        pd.Series([0.1, np.nan, 0.2]),
        pd.Series([0.1, np.inf]),
        pd.Series([0.1, -1.01]),
        pd.Series([0.1, "invalid"]),
    ],
)
def test_rejects_invalid_cumulative_return_inputs(values) -> None:
    with pytest.raises(ValueError):
        calculate_cumulative_returns(values)


def test_cumulative_returns_requires_series() -> None:
    with pytest.raises(TypeError, match="Series"):
        calculate_cumulative_returns([0.1, 0.1])
