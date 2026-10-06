"""Pinned ib-insync 0.9.86 boundary. / 固定版本的原始 callback 与 I/O 边界。"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from queue import Empty, SimpleQueue
from typing import Protocol, TYPE_CHECKING
from uuid import uuid4

from ib_insync import IB, Contract, Order
from ib_insync.client import Client
from ib_insync.wrapper import Wrapper

from broker.ibkr.config import PaperExecutionConfig, PaperSafetyError
from broker.ibkr.models import CommissionEvent, ErrorEvent, ExecutionEvent, OpenOrderEvent, SessionEvent, StatusEvent

if TYPE_CHECKING:
    from broker.ibkr.observation import RawBrokerSnapshot


RawEvent = OpenOrderEvent | StatusEvent | ExecutionEvent | CommissionEvent | ErrorEvent | SessionEvent


@dataclass(frozen=True)
class SessionEvidence:
    """Current connection evidence, not proof inferred from a port.

    每次调用重新检查实际账户和 generation；失效后不允许自动重连续发。
    """

    generation: str
    connected: bool
    host: str
    port: int
    client_id: int
    managed_accounts: tuple[str, ...]

    def validate(self, config: PaperExecutionConfig, generation: str) -> None:
        """Reject stale or mismatched sessions. / 拒绝过期或不匹配的连接证据。"""
        if (not self.connected or not self.generation or self.generation != generation
                or self.host != config.host or self.port != config.port
                or self.client_id != config.client_id or self.managed_accounts != (config.account,)):
            raise PaperSafetyError("session endpoint, generation or managed account mismatch.")


class IBKRTransport(Protocol):
    """Only the external client is replaced by offline fakes. / 离线只替换外部客户端。

    preflight failure proves no send entry; exceptions after place/cancel entry mean unknown delivery.
    发送入口后的异常一律视为可能送达，不能根据异常类型自动重试。
    """

    generation: str

    def evidence(self) -> SessionEvidence: ...
    def preflight(self) -> None: ...
    def qualify(self, contract: Contract) -> tuple[Contract, ...]: ...
    def next_order_id(self) -> int: ...
    def place(self, contract: Contract, order: Order) -> None: ...
    def cancel(self, order: Order) -> None: ...


class RawCallbackWrapper(Wrapper):
    """Capture protocol callbacks before ib_insync's mutable/synthetic Trade processing.

    直接截取 decoder 调用的 wrapper 方法，不订阅高层 Trade.statusEvent。
    Copies are queued before super(); synthetic cancel/error status changes cannot masquerade as raw status.
    Callback normalization is pulled by the caller, so validation exceptions remain visible.
    """

    def __init__(self, ib: IB, generation: str, queue: SimpleQueue) -> None:
        super().__init__(ib)
        self.generation = generation
        self.raw_events = queue

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId,
                    parentId, lastFillPrice, clientId, whyHeld, mktCapPrice=0.0):
        self.raw_events.put(StatusEvent(self.generation, clientId, orderId, permId, status,
                                        filled, remaining, datetime.now(timezone.utc)))
        super().orderStatus(orderId, status, filled, remaining, avgFillPrice, permId,
                            parentId, lastFillPrice, clientId, whyHeld, mktCapPrice)

    def openOrder(self, orderId, contract, order, orderState):
        self.raw_events.put(OpenOrderEvent(
            self.generation, order.account, order.clientId, orderId, order.permId,
            contract.conId, contract.symbol, contract.secType, contract.currency,
            order.action, order.totalQuantity, order.orderType, order.orderRef,
            orderState.status, datetime.now(timezone.utc)))
        super().openOrder(orderId, contract, order, orderState)

    def execDetails(self, reqId, contract, execution):
        self.raw_events.put(ExecutionEvent(
            self.generation, execution.acctNumber, execution.clientId, execution.orderId,
            execution.permId, execution.execId, contract.conId, contract.symbol,
            contract.secType, contract.currency, execution.side, execution.shares,
            Decimal(str(execution.price)), execution.time, datetime.now(timezone.utc)))
        super().execDetails(reqId, contract, execution)

    def commissionReport(self, commissionReport):
        # 中文：仅真实 callback 生成佣金事件，不读取 execDetails 的默认 CommissionReport。
        # English: Only this callback creates a commission event, never the execution placeholder.
        self.raw_events.put(CommissionEvent(
            self.generation, commissionReport.execId, Decimal(str(commissionReport.commission)),
            commissionReport.currency, datetime.now(timezone.utc)))
        super().commissionReport(commissionReport)

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        self.raw_events.put(ErrorEvent(self.generation, reqId, errorCode, errorString,
                                       datetime.now(timezone.utc), advancedOrderRejectJson))
        super().error(reqId, errorCode, errorString, advancedOrderRejectJson)


class ReadOnlyIBKRTransport:
    """Owned observation session; real order I/O is unconditionally locked in Phase 3H.

    内存 claim 无 crash durability，也没有可靠自动 Paper 证明，所以真实 place/cancel 拒绝执行。
    No configuration flag bypasses this lock. Phase 3I must add reviewed durability/recovery first.
    """

    def __init__(self, config: PaperExecutionConfig) -> None:
        import ib_insync

        if ib_insync.__version__ != "0.9.86":
            raise RuntimeError("transport requires verified ib-insync 0.9.86.")
        self.config = config
        self.generation = str(uuid4())
        self._events: SimpleQueue[RawEvent] = SimpleQueue()
        self._ib = IB()
        # 中文：只在未连接的自有实例中安装 wrapper，绝不修改共享行情 IB。
        # English: Install only on an owned, disconnected IB; never patch the market-data session.
        self._ib.wrapper = RawCallbackWrapper(self._ib, self.generation, self._events)
        self._ib.client = Client(self._ib.wrapper)
        self._ib.client.apiEnd += self._ib.disconnectedEvent
        self._ib.disconnectedEvent += self._on_disconnected
        self._valid = False
        self._connected_once = False
        self._query_started = False

    def _on_disconnected(self) -> None:
        self._valid = False
        self._events.put(SessionEvent(self.generation, datetime.now(timezone.utc), "session disconnected"))

    def connect_readonly(self, *, integration_opt_in: bool = False) -> None:
        """Explicit connectivity-only opt-in; reject reuse after disconnect.

        仅连接/查询，必须显式 opt-in；失败清理连接，不自动重连。
        """
        if integration_opt_in is not True:
            raise PaperSafetyError("explicit read-only integration opt-in is required.")
        self.config.validate(side_effect=False)
        if self._connected_once:
            raise PaperSafetyError("create a fresh session after disconnect; recovery is unsupported.")
        self._connected_once = True
        try:
            self._ib.connect(self.config.host, self.config.port, clientId=self.config.client_id,
                             readonly=True, account=self.config.account, timeout=10)
            self._valid = True
            self.evidence().validate(self.config, self.generation)
        except BaseException:
            self.close()
            raise

    def evidence(self) -> SessionEvidence:
        """Read current session facts. / 读取当前会话事实，不发网络请求。"""
        return SessionEvidence(self.generation, self._valid and self._ib.isConnected(),
                               self._ib.client.host, self._ib.client.port, self._ib.client.clientId,
                               tuple(self._ib.managedAccounts()))

    def preflight(self) -> None:
        """Always fail closed for real orders in this foundation. / 本阶段真实订单始终锁闭。"""
        raise PaperSafetyError("Phase 3H real order transport is locked: no crash-durable execution/recovery.")

    def query_snapshot(self) -> "RawBrokerSnapshot":
        """One explicit bounded read-only query; retain raw callbacks for audit.

        只查询、不绑定/接管订单；原始队列不清空。查询完成不保证历史 execution 全量可见。
        """
        from broker.ibkr.observation import RawBrokerSnapshot
        from ib_insync import ExecutionFilter

        self.config.validate(side_effect=False)
        self.evidence().validate(self.config, self.generation)
        if self._query_started:
            raise PaperSafetyError("use a fresh observation session for another query")
        self._query_started = True
        # Keep pre-query callbacks for ingestion, but never present them as current
        # open-order query results. / 历史队列保留，不冒充本次 broker 查询结果。
        prior = self.read_events()
        try:
            self._ib.RequestTimeout = 10
            self._ib.reqAllOpenOrders()
            self._ib.reqExecutions(ExecutionFilter(acctCode=self.config.account))
            self.evidence().validate(self.config, self.generation)
        finally:
            events = self.read_events()
            for event in (*prior, *events):
                self._events.put(event)
        uncertain = any(isinstance(e, (ErrorEvent, SessionEvent)) for e in events)
        return RawBrokerSnapshot(str(uuid4()), self.generation, self.config.account, datetime.now(timezone.utc),
                                 tuple(e for e in events if isinstance(e, OpenOrderEvent)),
                                 tuple(e for e in events if isinstance(e, StatusEvent)),
                                 tuple(e for e in events if isinstance(e, ExecutionEvent)),
                                 not uncertain, "QUERY_DIAGNOSTIC" if uncertain else "")

    def qualify(self, contract: Contract) -> tuple[Contract, ...]:
        """Query a contract only in an explicitly opened session. / 仅在显式连接内查询合约。"""
        self.evidence().validate(self.config, self.generation)
        return tuple(self._ib.qualifyContracts(contract))

    def next_order_id(self) -> int:
        """Unavailable while real execution is locked. / 真实执行锁闭时不分配订单 ID。"""
        self.preflight()
        raise AssertionError("unreachable")

    def place(self, contract: Contract, order: Order) -> None:
        """Reject real submission regardless of opt-in. / 无论 opt-in 如何均拒绝真实提交。"""
        self.preflight()

    def cancel(self, order: Order) -> None:
        """Reject real cancellation regardless of opt-in. / 无论 opt-in 如何均拒绝真实撤单。"""
        self.preflight()

    def read_events(self) -> tuple[RawEvent, ...]:
        """Drain immutable raw diagnostics; caller owns retention and normalization.

        取出原始快照；调用方必须保留并显式归一化，不存在自动 consumer/runner。
        """
        events = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except Empty:
                return tuple(events)

    def close(self) -> None:
        """Invalidate and disconnect the owned session. / 失效并关闭自有连接。"""
        self._valid = False
        self._ib.disconnect()
