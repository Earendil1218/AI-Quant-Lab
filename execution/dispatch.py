"""Process-lifetime attempt claims. / 仅在进程生命周期内有效的 attempt claim。"""

from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from execution.adapter import DispatchOperation
from execution.models import ClientOrderId, ExecutionOrder, ExecutionOrderState
from execution.repository import ExecutionOrderRepository


@dataclass(frozen=True)
class AttemptClaim:
    """Evidence of consumed intent, never a reusable send token. / 已消费意图的记录，不是可复用令牌。"""

    order: ExecutionOrder
    operation: DispatchOperation


class AttemptClaims(Protocol):
    """Atomically consume a saved logical operation or raise.

    原子消费已保存的逻辑操作；失败必须禁止外部调用。实现需说明持久性边界。
    Implementations must document durability and reject stale/unpersisted intent.
    """

    def claim(self, order: ExecutionOrder, operation: DispatchOperation) -> AttemptClaim: ...

    def validate(self, order: ExecutionOrder, operation: DispatchOperation) -> None: ...

    def verify_current(self, order: ExecutionOrder, operation: DispatchOperation) -> None: ...


class StaleIntentError(ValueError):
    """Saved intent differs from preparation. / 保存的意图已不同于准备时快照。"""


class InMemoryAttemptClaims:
    """Shared across adapters using one repository; no crash durability.

    多 adapter 必须共享同一实例；锁保护并发领取，没有 lease/retry/reset。
    Share one instance per execution scope. The lock protects claim races only;
    application state writes must be serialized with dispatch by the caller.
    """

    def __init__(self, repository: ExecutionOrderRepository) -> None:
        self._repository = repository
        self._lock = Lock()
        self._claims: dict[tuple[ClientOrderId, DispatchOperation], AttemptClaim] = {}

    def _validate(self, order: ExecutionOrder, operation: DispatchOperation) -> None:
        if not isinstance(order, ExecutionOrder) or not isinstance(operation, DispatchOperation):
            raise TypeError("claim requires an ExecutionOrder and DispatchOperation.")
        required = (ExecutionOrderState.SUBMISSION_PENDING if operation is DispatchOperation.SUBMIT
                    else ExecutionOrderState.CANCEL_PENDING)
        if order.state is not required or order.authorization is None:
            raise ValueError("claim requires authorized pending intent.")
        if operation is DispatchOperation.CANCEL and order.broker_order_id is None:
            raise ValueError("cancellation requires a bound broker identity.")
        if self._repository.get(order.client_order_id) != order:
            raise StaleIntentError("pending intent is not the current saved order.")
        if (order.client_order_id, operation) in self._claims:
            raise ValueError("operation already claimed; automatic retry is forbidden.")

    def validate(self, order: ExecutionOrder, operation: DispatchOperation) -> None:
        """Check saved authority without consuming intent. / 验证已保存授权，不消费意图。"""
        with self._lock:
            self._validate(order, operation)

    def claim(self, order: ExecutionOrder, operation: DispatchOperation) -> AttemptClaim:
        with self._lock:
            # 中文：准备完成后，在同一锁内重验完整快照并消费；过期准备不会占用 claim。
            # English: Revalidate the full prepared snapshot and consume atomically; stale intent consumes nothing.
            self._validate(order, operation)
            key = order.client_order_id, operation
            claim = AttemptClaim(order, operation)
            # 中文：发送前消费，未知结果也不释放；内存记录不提供 crash durability。
            # English: Consume before send and never release on uncertainty; memory is not durable.
            self._claims[key] = claim
            return claim

    def verify_current(self, order: ExecutionOrder, operation: DispatchOperation) -> None:
        """Recheck after external preparation; never renew or release a claim.

        qualification 后再次核对保存快照；不会刷新 claim，也不替代调用方的串行写入约定。
        """
        with self._lock:
            if self._claims.get((order.client_order_id, operation)) != AttemptClaim(order, operation):
                raise ValueError("operation has no matching consumed claim.")
            if self._repository.get(order.client_order_id) != order:
                raise ValueError("saved order changed after claim; dispatch is forbidden.")
