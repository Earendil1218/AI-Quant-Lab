"""Explicit disabled-by-default execution configuration. / 默认关闭的执行配置。"""

from dataclasses import dataclass
from os import environ
from typing import Mapping


class PaperSafetyError(ValueError):
    """Unverified environment; never fall back. / 环境未验证，禁止降级放行。"""


@dataclass(frozen=True)
class PaperExecutionConfig:
    """Separate from historical settings; account IDs are deployment inputs.

    端口与 DU 前缀都不是 Paper 证明；allowlist 必须来自独立核验。
    Configuration is intent, not proof of account type or permission to trade.
    ReadOnlyIBKRTransport stays locked; Phase 3K uses a separate explicit boundary.
    """

    mode: str = "DISABLED"
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 3
    account: str = ""
    paper_account_allowlist: tuple[str, ...] = ()
    allow_side_effects: bool = False

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> "PaperExecutionConfig":
        """Read explicit values without mutating historical config. / 读取显式环境值，不修改行情配置。"""
        values = environ if values is None else values
        return cls(
            mode=values.get("IBKR_TRADING_MODE", "DISABLED"),
            host=values.get("IBKR_EXECUTION_HOST", "127.0.0.1"),
            port=int(values.get("IBKR_EXECUTION_PORT", "7497")),
            client_id=int(values.get("IBKR_EXECUTION_CLIENT_ID", "3")),
            account=values.get("IBKR_PAPER_ACCOUNT", ""),
            paper_account_allowlist=tuple(filter(None, values.get("IBKR_PAPER_ACCOUNT_ALLOWLIST", "").split(","))),
            allow_side_effects=values.get("ALLOW_IBKR_PAPER_ORDER_SIDE_EFFECTS") == "YES",
        )

    def validate(self, *, side_effect: bool) -> None:
        """Fail closed on ambiguous mode, endpoint, account or execution intent.

        任一条件不明确就拒绝；这里只校验配置，session 仍需校验实际账户。
        This validates configuration only; session evidence is checked separately.
        """
        if self.mode != "PAPER":
            raise PaperSafetyError("execution mode must explicitly be PAPER.")
        if self.host not in {"127.0.0.1", "localhost", "::1"}:
            raise PaperSafetyError("Phase 3H requires a local dedicated TWS endpoint.")
        if type(self.port) is not int or self.port != 7497:
            raise PaperSafetyError("Phase 3H supports only the configured TWS paper port 7497.")
        if type(self.client_id) is not int or self.client_id <= 0:
            raise PaperSafetyError("execution requires a nonzero dedicated client ID.")
        if (not isinstance(self.account, str) or not self.account
                or self.account != self.account.strip()
                or not isinstance(self.paper_account_allowlist, tuple)
                or self.paper_account_allowlist != (self.account,)):
            raise PaperSafetyError("one independently verified paper account must be allowlisted exactly.")
        if side_effect and self.allow_side_effects is not True:
            raise PaperSafetyError("explicit paper order side-effect opt-in is required.")
