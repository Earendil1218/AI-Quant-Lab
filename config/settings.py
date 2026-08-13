"""集中管理项目运行配置。"""

from __future__ import annotations

import os


IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "7497"))
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "2"))

DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "NVDA")
DEFAULT_DURATION = os.getenv("DEFAULT_DURATION", "1 Y")
DEFAULT_BAR_SIZE = os.getenv("DEFAULT_BAR_SIZE", "1 day")
