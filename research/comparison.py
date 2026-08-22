"""基于共同日期样本进行基准和相关性研究。Benchmark and correlation research."""

from __future__ import annotations

from math import sqrt
from collections.abc import Mapping

import pandas as pd

from research.alignment import _normalize_symbol, align_return_series
from research.returns import calculate_cumulative_returns
from research.statistics import TRADING_DAYS_PER_YEAR, _validate_periods_per_year


def _align_asset_and_benchmark(
    asset_returns: pd.Series,
    benchmark_returns: pd.Series,
    asset_symbol: str,
    benchmark_symbol: str,
) -> tuple[pd.DataFrame, str, str]:
    normalized_asset = _normalize_symbol(asset_symbol)
    normalized_benchmark = _normalize_symbol(benchmark_symbol)
    if normalized_asset == normalized_benchmark:
        raise ValueError(
            "asset 与 benchmark symbol 必须不同。"
            "Asset and benchmark symbols must be distinct."
        )

    aligned = align_return_series(
        {
            normalized_asset: asset_returns,
            normalized_benchmark: benchmark_returns,
        }
    )
    return aligned, normalized_asset, normalized_benchmark


def calculate_active_returns(
    asset_returns: pd.Series,
    benchmark_returns: pd.Series,
    asset_symbol: str,
    benchmark_symbol: str,
) -> pd.Series:
    """在共同日期上计算资产减基准的周期主动收益。Calculate aligned active returns."""
    aligned, asset, benchmark = _align_asset_and_benchmark(
        asset_returns,
        benchmark_returns,
        asset_symbol,
        benchmark_symbol,
    )
    active_returns = aligned[asset] - aligned[benchmark]
    active_returns.name = f"{asset}_minus_{benchmark}_active_return"
    return active_returns.astype("float64")


def compare_cumulative_performance(
    asset_returns: pd.Series,
    benchmark_returns: pd.Series,
    asset_symbol: str,
    benchmark_symbol: str,
) -> pd.DataFrame:
    """从同一共同样本起点比较资产与基准的复合累计收益。Compare cumulative performance."""
    aligned, asset, benchmark = _align_asset_and_benchmark(
        asset_returns,
        benchmark_returns,
        asset_symbol,
        benchmark_symbol,
    )
    cumulative = pd.DataFrame(
        {
            asset: calculate_cumulative_returns(aligned[asset]),
            benchmark: calculate_cumulative_returns(aligned[benchmark]),
        },
        index=aligned.index,
    )
    cumulative.index.name = "date"
    return cumulative.astype("float64")


def calculate_annualized_tracking_error(
    asset_returns: pd.Series,
    benchmark_returns: pd.Series,
    asset_symbol: str,
    benchmark_symbol: str,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """用主动收益的样本标准差计算年化跟踪误差。Calculate annualized tracking error."""
    _validate_periods_per_year(periods_per_year)
    active_returns = calculate_active_returns(
        asset_returns,
        benchmark_returns,
        asset_symbol,
        benchmark_symbol,
    )
    return float(active_returns.std(ddof=1) * sqrt(periods_per_year))


def calculate_return_correlation(
    returns_by_symbol: Mapping[str, pd.Series],
) -> pd.DataFrame:
    """用统一共同日期样本计算 Pearson 收益相关矩阵。Calculate aligned Pearson correlation."""
    aligned = align_return_series(returns_by_symbol)
    correlation = aligned.corr(method="pearson")
    return correlation.astype("float64")
