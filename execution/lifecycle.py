"""Pure execution lifecycle transitions. / 纯执行生命周期转换。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from execution.models import (
    BrokerOrderId,
    BrokerOrderObservation,
    BrokerRejection,
    ClientOrderId,
    ExecutionFill,
    ExecutionOrder,
    ExecutionOrderState,
    ReconciliationIssue,
    ReconciliationIssueKind,
    ReconciliationResult,
    SubmissionAuthorization,
)
from risk.models import RiskDecision, RiskDecisionStatus
from trading.orders import OrderRequest


def create_execution_order(
    request: OrderRequest,
    created_at: datetime,
    client_order_id: ClientOrderId | None = None,
) -> ExecutionOrder:
    """Create one stable logical execution. / 创建一个身份稳定的逻辑执行订单。"""
    if not isinstance(request, OrderRequest):
        raise TypeError("request must be an OrderRequest.")
    if not isinstance(created_at, datetime):
        raise TypeError("created_at must be a datetime.")
    identity = ClientOrderId.generate() if client_order_id is None else client_order_id
    if not isinstance(identity, ClientOrderId):
        raise TypeError("client_order_id must be a ClientOrderId or None.")
    return ExecutionOrder(identity, request, ExecutionOrderState.CREATED, created_at, created_at)


def authorize_execution_order(
    order: ExecutionOrder,
    risk_decision: RiskDecision,
    authorization: SubmissionAuthorization,
) -> ExecutionOrder:
    """Bind explicit authority after risk approval. / 风控通过后绑定显式提交授权。"""
    _require_state(order, ExecutionOrderState.CREATED)
    if not isinstance(risk_decision, RiskDecision):
        raise TypeError("risk_decision must be a RiskDecision.")
    if not isinstance(authorization, SubmissionAuthorization):
        raise TypeError("authorization must be a SubmissionAuthorization.")
    if risk_decision.status is not RiskDecisionStatus.APPROVED:
        raise ValueError("risk decision must be APPROVED before authorization.")
    if risk_decision.request != order.request or authorization.request != order.request:
        raise ValueError("risk decision and authorization must bind the execution request.")
    if authorization.client_order_id != order.client_order_id:
        raise ValueError("authorization must bind the execution ClientOrderId.")
    return _advance(
        order,
        ExecutionOrderState.AUTHORIZED,
        authorization.authorized_at,
        authorization=authorization,
    )


def begin_submission(order: ExecutionOrder, submitted_at: datetime) -> ExecutionOrder:
    """Persist submission intent before any external side effect. / 外部副作用前持久化提交意图。"""
    _require_state(order, ExecutionOrderState.AUTHORIZED)
    if order.authorization is None:
        raise ValueError("submission requires explicit authorization.")
    return _advance(order, ExecutionOrderState.SUBMISSION_PENDING, submitted_at)


def record_submitted(order: ExecutionOrder, recorded_at: datetime) -> ExecutionOrder:
    if order.state is ExecutionOrderState.SUBMITTED:
        return order
    _require_state(order, ExecutionOrderState.SUBMISSION_PENDING, ExecutionOrderState.UNKNOWN)
    return _advance(order, ExecutionOrderState.SUBMITTED, recorded_at)


def record_acknowledgement(
    order: ExecutionOrder, broker_order_id: BrokerOrderId, acknowledged_at: datetime
) -> ExecutionOrder:
    if not isinstance(broker_order_id, BrokerOrderId):
        raise TypeError("broker_order_id must be a BrokerOrderId.")
    if order.broker_order_id is not None and order.broker_order_id != broker_order_id:
        raise ValueError("execution order is already bound to a different BrokerOrderId.")
    if order.state is ExecutionOrderState.ACKNOWLEDGED:
        return order
    _require_state(order, ExecutionOrderState.SUBMITTED, ExecutionOrderState.UNKNOWN)
    return _advance(
        order,
        ExecutionOrderState.ACKNOWLEDGED,
        acknowledged_at,
        broker_order_id=broker_order_id,
    )


def record_submission_unknown(order: ExecutionOrder, recorded_at: datetime) -> ExecutionOrder:
    if order.state is ExecutionOrderState.UNKNOWN:
        return order
    _require_state(
        order,
        ExecutionOrderState.SUBMISSION_PENDING,
        ExecutionOrderState.SUBMITTED,
        ExecutionOrderState.CANCEL_PENDING,
    )
    return _advance(order, ExecutionOrderState.UNKNOWN, recorded_at)


def record_broker_rejection(
    order: ExecutionOrder, rejection: BrokerRejection
) -> ExecutionOrder:
    if not isinstance(rejection, BrokerRejection):
        raise TypeError("rejection must be a BrokerRejection.")
    if rejection.client_order_id != order.client_order_id:
        raise ValueError("rejection must bind the execution ClientOrderId.")
    if order.state is ExecutionOrderState.REJECTED:
        if order.broker_rejection == rejection:
            return order
        raise ValueError("execution order already has a different broker rejection.")
    _require_state(
        order,
        ExecutionOrderState.SUBMISSION_PENDING,
        ExecutionOrderState.SUBMITTED,
        ExecutionOrderState.UNKNOWN,
    )
    return _advance(
        order,
        ExecutionOrderState.REJECTED,
        rejection.rejected_at,
        broker_rejection=rejection,
    )


def record_fill(
    order: ExecutionOrder, execution_fill: ExecutionFill
) -> tuple[ExecutionOrder, bool]:
    """Record a fill and flag whether accounting may apply it. / 记录成交并标记能否首次入账。"""
    if not isinstance(execution_fill, ExecutionFill):
        raise TypeError("execution_fill must be an ExecutionFill.")
    if execution_fill.client_order_id != order.client_order_id:
        raise ValueError("fill must bind the execution ClientOrderId.")
    for existing in order.fills:
        same_fill_id = existing.fill_id == execution_fill.fill_id
        same_broker_id = (
            execution_fill.broker_execution_id is not None
            and existing.broker_execution_id == execution_fill.broker_execution_id
        )
        if same_fill_id or same_broker_id:
            if existing == execution_fill:
                return order, False
            raise ValueError("fill identity is already bound to different fill data.")
    _require_state(
        order,
        ExecutionOrderState.ACKNOWLEDGED,
        ExecutionOrderState.PARTIALLY_FILLED,
        ExecutionOrderState.CANCEL_PENDING,
        ExecutionOrderState.UNKNOWN,
    )
    fill = execution_fill.fill
    if fill.instrument != order.request.instrument:
        raise ValueError("fill instrument does not match the order request.")
    if fill.side is not order.request.side:
        raise ValueError("fill side does not match the order request.")
    cumulative = order.cumulative_filled_quantity + fill.quantity
    if cumulative > order.request.quantity:
        raise ValueError("fill would exceed the order quantity.")
    state = (
        ExecutionOrderState.FILLED
        if cumulative == order.request.quantity
        else ExecutionOrderState.PARTIALLY_FILLED
    )
    return (
        _advance(
            order,
            state,
            fill.filled_at,
            cumulative_filled_quantity=cumulative,
            fills=order.fills + (execution_fill,),
        ),
        True,
    )


def request_cancellation(order: ExecutionOrder, requested_at: datetime) -> ExecutionOrder:
    _require_state(
        order, ExecutionOrderState.ACKNOWLEDGED, ExecutionOrderState.PARTIALLY_FILLED
    )
    return _advance(order, ExecutionOrderState.CANCEL_PENDING, requested_at)


def record_cancelled(order: ExecutionOrder, cancelled_at: datetime) -> ExecutionOrder:
    if order.state is ExecutionOrderState.CANCELLED:
        return order
    _require_state(order, ExecutionOrderState.CANCEL_PENDING, ExecutionOrderState.UNKNOWN)
    return _advance(order, ExecutionOrderState.CANCELLED, cancelled_at)


def apply_broker_order_observation(
    order: ExecutionOrder, observation: BrokerOrderObservation
) -> ExecutionOrder:
    """Resolve UNKNOWN from a broker-neutral observation. / 用券商中立观察收敛未知状态。"""
    if not isinstance(observation, BrokerOrderObservation):
        raise TypeError("observation must be a BrokerOrderObservation.")
    if observation.client_order_id != order.client_order_id:
        raise ValueError("observation must bind the execution ClientOrderId.")
    if order.state is not ExecutionOrderState.UNKNOWN:
        same_identity = (
            observation.broker_order_id is None
            or observation.broker_order_id == order.broker_order_id
        )
        same_quantity = (
            observation.cumulative_filled_quantity
            == order.cumulative_filled_quantity
        )
        if order.state is observation.state and same_identity and same_quantity:
            return order
        raise ValueError("broker observations may resolve only UNKNOWN orders.")
    if observation.state is ExecutionOrderState.SUBMITTED:
        return record_submitted(order, observation.observed_at)
    if observation.state is ExecutionOrderState.ACKNOWLEDGED:
        if observation.broker_order_id is None:
            raise ValueError("acknowledgement observation requires BrokerOrderId.")
        return record_acknowledgement(
            order, observation.broker_order_id, observation.observed_at
        )
    if observation.state is ExecutionOrderState.REJECTED:
        return _advance(order, ExecutionOrderState.REJECTED, observation.observed_at)
    if observation.state is ExecutionOrderState.CANCELLED:
        return record_cancelled(order, observation.observed_at)
    if observation.state in {
        ExecutionOrderState.PARTIALLY_FILLED,
        ExecutionOrderState.FILLED,
    }:
        if observation.cumulative_filled_quantity <= 0:
            raise ValueError("fill observation requires positive cumulative quantity.")
        expected_filled = observation.state is ExecutionOrderState.FILLED
        if expected_filled != (
            observation.cumulative_filled_quantity == order.request.quantity
        ):
            raise ValueError("observation state and cumulative quantity disagree.")
        if observation.cumulative_filled_quantity > order.request.quantity:
            raise ValueError("observation would overfill the order.")
        return _advance(
            order,
            observation.state,
            observation.observed_at,
            broker_order_id=observation.broker_order_id,
            cumulative_filled_quantity=observation.cumulative_filled_quantity,
        )
    raise ValueError("observation cannot resolve UNKNOWN to the requested state.")


def reconcile_order(
    order: ExecutionOrder, observation: BrokerOrderObservation | None
) -> ReconciliationResult:
    if observation is None:
        kind = (
            ReconciliationIssueKind.UNRESOLVED_SUBMISSION
            if order.state is ExecutionOrderState.UNKNOWN
            else ReconciliationIssueKind.LOCAL_ORDER_MISSING_AT_BROKER
        )
        return ReconciliationResult(
            (ReconciliationIssue(kind, order.client_order_id, "No broker observation."),)
        )
    if observation.client_order_id != order.client_order_id:
        return ReconciliationResult(
            (
                ReconciliationIssue(
                    ReconciliationIssueKind.BROKER_ORDER_UNKNOWN_LOCALLY,
                    observation.client_order_id,
                    "Observation does not match the local order.",
                ),
            )
        )
    issues: list[ReconciliationIssue] = []
    if order.state is not ExecutionOrderState.UNKNOWN and order.state is not observation.state:
        issues.append(
            ReconciliationIssue(
                ReconciliationIssueKind.STATE_MISMATCH,
                order.client_order_id,
                f"Local {order.state.value}; broker {observation.state.value}.",
            )
        )
    if order.cumulative_filled_quantity != observation.cumulative_filled_quantity:
        issues.append(
            ReconciliationIssue(
                ReconciliationIssueKind.FILL_QUANTITY_MISMATCH,
                order.client_order_id,
                "Local and broker cumulative fill quantities differ.",
            )
        )
    return ReconciliationResult(tuple(issues))


def _require_state(order: ExecutionOrder, *allowed: ExecutionOrderState) -> None:
    if not isinstance(order, ExecutionOrder):
        raise TypeError("order must be an ExecutionOrder.")
    if order.state not in allowed:
        choices = ", ".join(state.value for state in allowed)
        raise ValueError(f"state {order.state.value} cannot transition; expected {choices}.")


def _advance(
    order: ExecutionOrder,
    state: ExecutionOrderState,
    updated_at: datetime,
    **changes: object,
) -> ExecutionOrder:
    if not isinstance(updated_at, datetime):
        raise TypeError("transition timestamp must be a datetime.")
    if updated_at < order.updated_at:
        raise ValueError("transition timestamp must not precede updated_at.")
    return replace(
        order,
        state=state,
        updated_at=updated_at,
        version=order.version + 1,
        **changes,
    )
