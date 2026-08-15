"""集中管理项目运行配置。"""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"


IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "7497"))
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "2"))

DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "NVDA")
DEFAULT_DURATION = os.getenv("DEFAULT_DURATION", "1 Y")
DEFAULT_BAR_SIZE = os.getenv("DEFAULT_BAR_SIZE", "1 day")
