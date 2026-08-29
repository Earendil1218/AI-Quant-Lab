"""Pure, date-aware market indicators. / 纯内存、日期化市场指标。"""

from __future__ import annotations

import pandas as pd

from data.validation import validate_market_data


def _validate_window(window: int) -> None:
    if isinstance(window, bool) or not isinstance(window, int):
        raise TypeError("window must be an integer (bool is not accepted).")
    if window <= 0:
        raise ValueError("window must be positive.")


def calculate_moving_average(
    frame: pd.DataFrame,
    window: int,
    *,
    price_column: str = "close",
) -> pd.Series:
    """Calculate a trailing simple moving average using complete windows only."""
    validate_market_data(frame)
    _validate_window(window)
    if not isinstance(price_column, str):
        raise TypeError("price_column must be a string.")
    if price_column not in ("open", "high", "low", "close"):
        raise ValueError("price_column must be one of open, high, low, or close.")

    parsed_dates = pd.to_datetime(frame["date"])
    if getattr(parsed_dates.dt, "tz", None) is not None:
        raise ValueError("date must be timezone-naive for daily research data.")

    dates = pd.DatetimeIndex(parsed_dates, name="date")
    prices = pd.Series(
        pd.to_numeric(frame[price_column]).to_numpy(dtype="float64"),
        index=dates,
    )
    result = prices.rolling(window=window, min_periods=window).mean()
    result.name = f"{price_column}_moving_average_{window}"
    return result.astype("float64")
