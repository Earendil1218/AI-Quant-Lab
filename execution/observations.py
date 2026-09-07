"""Explicit asynchronous event rules. / 显式异步事件规则，不提供任意状态跳转。"""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from execution.adapter import DispatchOutcome, DispatchResult
from execution.lifecycle import _advance, record_fill
from execution.models import (
    BrokerOrderId, BrokerRejection, ClientOrderId, ExecutionFill,
    ExecutionOrder, ExecutionOrderState as State, TERMINAL_EXECUTION_STATES,
)
from trading import OrderRequest


class ObservationKind(str, Enum):
    """Facts independent of broker vocabulary. / 不依赖 broker 词汇的事实类型。"""

    PENDING = "pending"
    WORKING = "working"
    HELD = "held"
    COMPLETION = "completion"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    EXECUTION_PENDING = "execution_pending"
    FILL = "fill"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"
    CONNECTION_LOST = "connection_lost"
    INFORMATION = "information"


@dataclass(frozen=True)
class ExecutionObservation:
    """Validated broker fact with local receipt time, never an accounting snapshot.

    request/身份绑定不可变；reported quantity 仅供核对，只有 execution_fill 可以入账。
    Broker completion and unpaired executions remain visible without inventing economic fills.
    """

    client_order_id: ClientOrderId
    request: OrderRequest
    kind: ObservationKind
    observed_at: datetime
    broker_order_id: BrokerOrderId | None = None
    reported_filled_quantity: int | None = None
    execution_fill: ExecutionFill | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.client_order_id, ClientOrderId) or not isinstance(self.request, OrderRequest):
            raise TypeError("observation requires typed identity and request.")
        if not isinstance(self.kind, ObservationKind) or not isinstance(self.observed_at, datetime):
            raise TypeError("observation requires typed kind and local receipt time.")
        if self.broker_order_id is not None and not isinstance(self.broker_order_id, BrokerOrderId):
            raise TypeError("broker_order_id must be a BrokerOrderId.")
        quantity = self.reported_filled_quantity
        if quantity is not None and (type(quantity) is not int or not 0 <= quantity <= self.request.quantity):
            raise ValueError("reported quantity must be an integer within order quantity.")
        if (self.kind is ObservationKind.FILL) != (self.execution_fill is not None):
            raise ValueError("only FILL observations require execution_fill.")
        if self.execution_fill is not None:
            fill = self.execution_fill
            if not isinstance(fill, ExecutionFill) or fill.client_order_id != self.client_order_id:
                raise ValueError("fill identity does not match observation.")
            if fill.fill.instrument != self.request.instrument or fill.fill.side is not self.request.side:
                raise ValueError("fill economics do not match observation request.")


@dataclass(frozen=True)
class ObservationApplication:
    """Caller must save before accounting; unresolved blocks further planning.

    调用方先保存再入账；unresolved 表示事实尚未完整，不能据此继续规划。
    This return value does not implement a repository/portfolio transaction.
    unresolved 仅描述本次事件，不是全局 readiness；调用方必须保留尚未解决的观察。
    unresolved is per-event, not a global readiness latch; callers retain unresolved observations.
    """

    order: ExecutionOrder
    fill_accepted: bool = False
    unresolved: bool = False


def apply_dispatch_result(order: ExecutionOrder, result: DispatchResult, applied_at: datetime) -> ExecutionOrder:
    """Uncertain delivery changes lifecycle only, preserving every known economic fact.

    UNKNOWN 仅表示未解决的生命周期结果；保留成交、身份、请求和授权，返回不等于确认。
    """
    if result.client_order_id != order.client_order_id:
        raise ValueError("dispatch result identity mismatch.")
    if result.outcome is not DispatchOutcome.DELIVERY_UNKNOWN:
        return order
    if order.state in TERMINAL_EXECUTION_STATES or order.state is State.UNKNOWN:
        return order
    if order.state not in {State.SUBMISSION_PENDING, State.SUBMITTED, State.ACKNOWLEDGED,
                           State.PARTIALLY_FILLED, State.CANCEL_PENDING}:
        raise ValueError("uncertain delivery requires an in-flight order.")
    return _advance(order, State.UNKNOWN, applied_at)


def apply_execution_observation(
    order: ExecutionOrder, observation: ExecutionObservation, *, applied_at: datetime,
) -> ObservationApplication:
    """Apply a validated fact with explicit source-state rules, advancing at most one version.

    验证身份及请求；本地 applied_at 必须单调且不早于接收时间。只由配对 Fill 累计数量。
    Account/session validation belongs to the adapter; this layer verifies neutral bindings.
    Duplicate fills/statuses are idempotent; conflicting identity always raises.
    """
    if not isinstance(observation, ExecutionObservation):
        raise TypeError("observation must be an ExecutionObservation.")
    if observation.client_order_id != order.client_order_id or observation.request != order.request:
        raise ValueError("observation identity/request mismatch.")
    bid = observation.broker_order_id
    if order.broker_order_id is not None and bid is not None and bid != order.broker_order_id:
        raise ValueError("conflicting broker identity.")
    if applied_at < order.updated_at or applied_at < observation.observed_at:
        raise ValueError("applied_at must not precede local state or receipt time.")
    if order.state in {State.CREATED, State.AUTHORIZED}:
        raise ValueError("broker event requires saved submission intent.")
    kind = observation.kind
    if kind is ObservationKind.INFORMATION:
        return ObservationApplication(order)
    if kind in {ObservationKind.PENDING, ObservationKind.HELD, ObservationKind.COMPLETION,
                ObservationKind.EXECUTION_PENDING, ObservationKind.UNRESOLVED}:
        # 中文：Filled status 不推进经济数量；保留观察，由 execDetails + commission 驱动。
        # English: Completion status never advances economic quantity; paired executions do.
        return ObservationApplication(order, unresolved=True)
    if kind is ObservationKind.CONNECTION_LOST:
        if order.state in TERMINAL_EXECUTION_STATES or order.state is State.UNKNOWN:
            return ObservationApplication(order, unresolved=True)
        # 中文：连接丢失不等于拒单；UNKNOWN 阻止重新提交，并保留已有经济成交。
        # English: Loss is not rejection; UNKNOWN blocks resubmission and preserves recorded economics.
        return ObservationApplication(_advance(order, State.UNKNOWN, applied_at), unresolved=True)
    if bid is None and kind is not ObservationKind.REJECTED:
        return ObservationApplication(order, unresolved=True)
    bound = replace(order, broker_order_id=bid or order.broker_order_id)
    if kind is ObservationKind.FILL:
        fill = observation.execution_fill
        assert fill is not None
        if fill.broker_execution_id is None:
            raise ValueError("broker fill requires execution provenance.")
        if fill.fill.filled_at < order.created_at:
            raise ValueError("execution time precedes order creation.")
        if order.state is State.REJECTED:
            raise ValueError("fill conflicts with rejection; manual reconciliation required.")
        # 中文：首个 callback 可以直接是成交；取消后的迟到成交必须携带同一稳定身份。
        # English: A fill can be the first callback; late cancelled fills require stable binding.
        if order.state is State.CANCELLED and order.broker_order_id != bid:
            raise ValueError("late fill requires an existing matching broker identity.")
        source = bound
        if order.state in {State.SUBMISSION_PENDING, State.SUBMITTED, State.CANCELLED}:
            source = replace(bound, state=State.ACKNOWLEDGED)
        updated, accepted = record_fill(source, fill, applied_at=applied_at)
        if not accepted:
            return ObservationApplication(order)
        if order.state is State.CANCELLED and updated.state is not State.FILLED:
            # 中文：CANCELLED 表示剩余未成交部分已取消，并不意味着从未成交。
            # English: CANCELLED means the unfilled remainder was cancelled, not that no fills occurred.
            updated = replace(updated, state=State.CANCELLED)
        return ObservationApplication(updated, fill_accepted=True)
    if kind is ObservationKind.WORKING:
        if order.state is State.REJECTED:
            return ObservationApplication(order, unresolved=True)
        if order.state in {State.SUBMISSION_PENDING, State.SUBMITTED, State.UNKNOWN}:
            target = State.PARTIALLY_FILLED if order.cumulative_filled_quantity else State.ACKNOWLEDGED
        else:
            # 中文：迟到 acknowledgement 不能回退已经推进的状态。
            # English: Delayed acknowledgement must never regress a later state.
            target = order.state
    elif kind is ObservationKind.CANCEL_PENDING:
        if order.state in TERMINAL_EXECUTION_STATES:
            return ObservationApplication(order)
        target = State.CANCEL_PENDING
    elif kind is ObservationKind.CANCELLED:
        if order.state is State.FILLED:
            return ObservationApplication(order)
        if order.state is State.REJECTED:
            raise ValueError("cancellation conflicts with rejection.")
        target = State.CANCELLED
    elif kind is ObservationKind.REJECTED:
        if order.state is State.REJECTED:
            if order.broker_rejection and order.broker_rejection.message == observation.detail:
                return ObservationApplication(order)
            raise ValueError("conflicting rejection.")
        if (order.state not in {State.SUBMISSION_PENDING, State.SUBMITTED, State.UNKNOWN}
                or order.cumulative_filled_quantity):
            raise ValueError("rejection conflicts with acknowledged execution; reconciliation required.")
        rejection = BrokerRejection(order.client_order_id, applied_at, None, observation.detail)
        return ObservationApplication(_advance(bound, State.REJECTED, applied_at, broker_rejection=rejection))
    else:
        raise ValueError("unsupported observation kind.")
    unresolved = (observation.reported_filled_quantity is not None
                  and observation.reported_filled_quantity != order.cumulative_filled_quantity)
    if target is order.state and bound == order:
        return ObservationApplication(order, unresolved=unresolved)
    return ObservationApplication(_advance(bound, target, applied_at), unresolved=unresolved)
