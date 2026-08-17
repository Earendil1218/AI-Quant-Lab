"""市场数据 DataFrame 与本地 CSV 文件之间的读写。"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from config.settings import RAW_DATA_DIR


_BAR_SIZE_INTERVALS = {
    "1 day": "1d",
}
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9.-]+$")


def build_market_data_path(
    symbol: str,
    bar_size: str,
    directory: Path = RAW_DATA_DIR,
) -> Path:
    """
    根据标的、K 线粒度和数据目录生成规范的 CSV 路径。

    Build a canonical CSV path from the symbol, bar size, and data directory.
    """
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol or not _SYMBOL_PATTERN.fullmatch(normalized_symbol):
        raise ValueError(f"无效的股票代码：{symbol!r}")

    normalized_bar_size = " ".join(bar_size.strip().lower().split())
    try:
        interval = _BAR_SIZE_INTERVALS[normalized_bar_size]
    except KeyError as exc:
        raise ValueError(f"不支持的 K 线粒度：{bar_size!r}") from exc

    return Path(directory) / f"{normalized_symbol}_{interval}.csv"


def save_market_data(frame: pd.DataFrame, path: Path) -> Path:
    """保存不含 index 的市场数据 CSV。Save market data without its index."""
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(csv_path, index=False)
    return csv_path


def load_market_data(path: Path) -> pd.DataFrame:
    """读取 CSV 并恢复 date 类型。Load CSV data and restore the date dtype."""
    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"市场数据文件不存在：{csv_path}")

    return pd.read_csv(csv_path, parse_dates=["date"])
