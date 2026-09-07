"""Broker-neutral dispatch contracts. / 与 broker 无关的发送边界。"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from execution.models import ClientOrderId, ExecutionOrder


class DispatchOperation(str, Enum):
    """One-shot operation, never an automatic retry. / 一次性操作，不包含自动重试。"""

    SUBMIT = "submit"
    CANCEL = "cancel"


class DispatchOutcome(str, Enum):
    """Transport evidence, not broker acceptance. / 传输证据，不代表 broker 接受。"""

    NOT_SENT = "not_sent"
    DISPATCH_RETURNED = "dispatch_returned"
    DELIVERY_UNKNOWN = "delivery_unknown"


@dataclass(frozen=True)
class DispatchResult:
    """Immutable outcome; the caller applies/persists observations separately.

    不修改订单；NOT_SENT 证明未进入发送入口，RETURNED 不是确认，UNKNOWN 禁止重试。
    NOT_SENT proves no send entry; RETURNED is no acknowledgement; UNKNOWN forbids retry.
    """

    client_order_id: ClientOrderId
    operation: DispatchOperation
    outcome: DispatchOutcome
    detail: str

    def __post_init__(self) -> None:
        if (not isinstance(self.client_order_id, ClientOrderId)
                or not isinstance(self.operation, DispatchOperation)
                or not isinstance(self.outcome, DispatchOutcome)):
            raise TypeError("dispatch result requires typed identity, operation and outcome.")
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise ValueError("dispatch detail must be nonempty.")


class ExecutionBrokerAdapter(Protocol):
    """Submit/cancel saved intent without owning aggregate persistence.

    提交或撤销已保存的意图；校验失败抛异常，传输不确定性通过结果返回。
    Validation raises; uncertain delivery returns a result for explicit application.
    """

    def submit(self, order: ExecutionOrder) -> DispatchResult: ...

    def cancel(self, order: ExecutionOrder) -> DispatchResult: ...
