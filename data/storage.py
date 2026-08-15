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
    """根据标的和 IBKR K 线粒度生成规范的 CSV 路径。"""
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
    """将市场数据保存为不包含 DataFrame index 的 CSV。"""
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(csv_path, index=False)
    return csv_path


def load_market_data(path: Path) -> pd.DataFrame:
    """从 CSV 读取市场数据，并将 date 列恢复为日期类型。"""
    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"市场数据文件不存在：{csv_path}")

    return pd.read_csv(csv_path, parse_dates=["date"])
