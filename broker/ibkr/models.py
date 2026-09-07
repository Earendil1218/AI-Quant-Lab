"""IBKR-private identities and immutable callback snapshots. / IBKR 私有身份与不可变回调快照。"""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
from threading import RLock
from uuid import NAMESPACE_URL, uuid5

from execution import BrokerExecutionId, BrokerOrderId, ClientOrderId, ExecutionFillId
from trading import OrderRequest


def integer(value: object, name: str, *, minimum: int = 0) -> int:
    """Reject fractional/nonfinite values rather than truncate. / 拒绝小数和无效值，禁止截断数量。"""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{name} must be an integer quantity.")
    number = Decimal(str(value))
    if not number.is_finite() or number != number.to_integral_value() or number < minimum:
        raise ValueError(f"{name} must be a finite integer >= {minimum}.")
    return int(number)


def execution_ids(account: str, exec_id: str) -> tuple[BrokerExecutionId, ExecutionFillId]:
    """Deterministic identity includes account and the complete execId.

    同一 execution 重放产生相同本地身份；不截断 execId，不用每次随机 UUID。
    """
    if not account or not exec_id or exec_id != exec_id.strip():
        raise ValueError("account and exact nonempty execId are required.")
    value = f"ibkr:{len(account)}:{account}:execution:{exec_id}"
    return BrokerExecutionId(value), ExecutionFillId(str(uuid5(NAMESPACE_URL, value)))


@dataclass(frozen=True)
class IBKROrderIdentity:
    """API ownership is distinct from host identity. / API ownership 与 host 身份分离。

    perm_id=0 means not yet known; only a positive permId becomes BrokerOrderId.
    perm_id=0 不绑定稳定身份；session_generation 阻止复用已失效连接。
    """

    account: str
    client_id: int
    order_id: int
    session_generation: str
    client_order_id: ClientOrderId
    perm_id: int = 0

    def __post_init__(self) -> None:
        if not self.account or not self.session_generation or not isinstance(self.client_order_id, ClientOrderId):
            raise ValueError("identity requires account, generation and ClientOrderId.")
        for name, minimum in (("client_id", 1), ("order_id", 1), ("perm_id", 0)):
            if type(getattr(self, name)) is not int or getattr(self, name) < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}.")

    @property
    def broker_order_id(self) -> BrokerOrderId | None:
        return (BrokerOrderId(f"ibkr:{len(self.account)}:{self.account}:perm:{self.perm_id}")
                if self.perm_id else None)


@dataclass(frozen=True)
class OrderBinding:
    """Request pinned to a qualified contract and immutable API identity. / 请求绑定已确认合约和 API 身份。"""

    identity: IBKROrderIdentity
    request: OrderRequest
    con_id: int


class IdentityRegistry:
    """One registry per session; reject conflicting forward and reverse bindings.

    仅内存身份索引；不提供 restart recovery。callback 不可自动认领外来订单。
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._bindings: dict[ClientOrderId, OrderBinding] = {}
        self._api: dict[tuple[str, int, int], ClientOrderId] = {}
        self._perms: dict[tuple[str, int], ClientOrderId] = {}

    def register(self, binding: OrderBinding) -> None:
        """Bind once, with identical replay allowed. / 只绑定一次，允许完全相同的重放。"""
        identity = binding.identity
        integer(binding.con_id, "con_id", minimum=1)
        key = identity.session_generation, identity.client_id, identity.order_id
        with self._lock:
            existing = self._bindings.get(identity.client_order_id)
            if existing is not None:
                if existing == binding:
                    return
                raise ValueError("conflicting local order binding.")
            if key in self._api:
                raise ValueError("API order already belongs to another local order.")
            if identity.perm_id and (identity.account, identity.perm_id) in self._perms:
                raise ValueError("permId already belongs to another local order.")
            self._bindings[identity.client_order_id] = binding
            self._api[key] = identity.client_order_id
            if identity.perm_id:
                self._perms[identity.account, identity.perm_id] = identity.client_order_id

    def get(self, client_order_id: ClientOrderId) -> OrderBinding:
        """Lookup an explicitly registered order or raise. / 查询显式注册的订单，否则失败。"""
        with self._lock:
            return self._bindings[client_order_id]

    def bindings(self) -> tuple[OrderBinding, ...]:
        """Immutable snapshot for session-wide uncertainty. / 返回会话不确定性处理所需的不可变快照。"""
        with self._lock:
            return tuple(self._bindings.values())

    def resolve(self, generation: str, client_id: int, order_id: int,
                perm_id: int, account: str | None = None) -> OrderBinding:
        """Validate ownership and bind a newly observed permId atomically.

        orderStatus 不含账户；只通过本 session 已注册映射推导账户，不能按 symbol 猜测。
        """
        perm_id = integer(perm_id, "perm_id")
        with self._lock:
            cid = self._api[generation, client_id, order_id]
            binding = self._bindings[cid]
            identity = binding.identity
            if account is not None and account != identity.account:
                raise ValueError("callback account mismatch.")
            if identity.perm_id and perm_id and identity.perm_id != perm_id:
                raise ValueError("conflicting permId.")
            if perm_id and not identity.perm_id:
                owner = self._perms.get((identity.account, perm_id))
                if owner is not None and owner != cid:
                    raise ValueError("permId already belongs to another local order.")
                binding = replace(binding, identity=replace(identity, perm_id=perm_id))
                self._bindings[cid] = binding
                self._perms[identity.account, perm_id] = cid
            return binding


class EventSource(str, Enum):
    """Raw broker callbacks and local synthetic notifications must remain distinct.

    原始 broker 回调与本地合成通知必须分离，后者不能确认订单状态。
    """

    BROKER = "broker"
    LOCAL = "local"


@dataclass(frozen=True)
class OpenOrderEvent:
    """Full broker order callback used to validate account and request correlation.

    完整订单回调用于核对账户、合约及 orderRef，不能自动认领不属于本系统的订单。
    """

    generation: str
    account: str
    client_id: int
    order_id: int
    perm_id: int
    con_id: int
    symbol: str
    sec_type: str
    currency: str
    side: str
    quantity: int
    order_type: str
    order_ref: str
    status: str
    observed_at: datetime


@dataclass(frozen=True)
class StatusEvent:
    """Raw orderStatus snapshot; quantities are not economic fills. / 状态快照中的数量不是经济成交。"""

    generation: str
    client_id: int
    order_id: int
    perm_id: int
    status: str
    filled: int
    remaining: int
    observed_at: datetime
    source: EventSource = EventSource.BROKER


@dataclass(frozen=True)
class ExecutionEvent:
    """Execution economics without invented commission. / 尚未伪造或补默认佣金的成交事实。"""

    generation: str
    account: str
    client_id: int
    order_id: int
    perm_id: int
    exec_id: str
    con_id: int
    symbol: str
    sec_type: str
    currency: str
    side: str
    shares: int
    price: Decimal
    execution_time: datetime
    observed_at: datetime


@dataclass(frozen=True)
class CommissionEvent:
    """Actual CommissionReport callback, not its default placeholder. / 实际佣金回调，不是默认占位对象。"""

    generation: str
    exec_id: str
    commission: Decimal
    currency: str
    observed_at: datetime


@dataclass(frozen=True)
class ErrorEvent:
    """Raw diagnostic payload remains inside broker boundary. / 原始诊断信息保留在 broker 边界内。"""

    generation: str
    request_id: int
    code: int
    message: str
    observed_at: datetime
    advanced_rejection: str = ""


@dataclass(frozen=True)
class SessionEvent:
    """Session loss is uncertainty, never rejection. / 会话丢失代表不确定，不是拒单。"""

    generation: str
    observed_at: datetime
    detail: str
