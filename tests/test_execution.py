"""Offline tests for the broker-neutral execution lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from execution import (
    BrokerExecutionId,
    BrokerOrderId,
    BrokerOrderObservation,
    BrokerRejection,
    ClientOrderId,
    ExecutionFill,
    ExecutionFillId,
    ExecutionOrderState,
    InMemoryExecutionOrderRepository,
    ReconciliationIssueKind,
    SubmissionAuthorization,
    apply_broker_order_observation,
    authorize_execution_order,
    begin_submission,
    create_execution_order,
    reconcile_order,
    record_acknowledgement,
    record_broker_rejection,
    record_cancelled,
    record_fill,
    record_submission_unknown,
    record_submitted,
    request_cancellation,
)
from risk import RiskDecision, RiskDecisionStatus, RiskRejectionReason
from trading import (
    AssetClass,
    ExecutionRejection,
    Fill,
    InstrumentId,
    OrderRequest,
    OrderSide,
)


T0 = datetime(2026, 9, 1, 9, 30)
NVDA = InstrumentId(AssetClass.EQUITY, "NVDA")
SPY = InstrumentId(AssetClass.EQUITY, "SPY")
CID = ClientOrderId("12345678-1234-5678-1234-567812345678")


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def request(quantity: int = 100) -> OrderRequest:
    return OrderRequest(NVDA, OrderSide.BUY, quantity, T0)


def created(quantity: int = 100):
    return create_execution_order(request(quantity), T0, CID)


def approved(order):
    return RiskDecision(RiskDecisionStatus.APPROVED, order.request, at(1))


def authorization(order, *, request_override=None):
    return SubmissionAuthorization(
        order.client_order_id,
        order.request if request_override is None else request_override,
        at(2),
        "operator:test",
    )


def authorized(quantity: int = 100):
    order = created(quantity)
    return authorize_execution_order(order, approved(order), authorization(order))


def acknowledged(quantity: int = 100):
    order = begin_submission(authorized(quantity), at(3))
    order = record_submitted(order, at(4))
    return record_acknowledgement(order, BrokerOrderId("broker-1"), at(5))


def execution_fill(
    fill_id: str,
    quantity: int,
    *,
    instrument: InstrumentId = NVDA,
    side: OrderSide = OrderSide.BUY,
    broker_execution_id: str | None = None,
    minute: int = 6,
) -> ExecutionFill:
    economic = Fill(
        instrument, side, quantity, at(minute), Decimal("100"), Decimal("1")
    )
    external = (
        None if broker_execution_id is None else BrokerExecutionId(broker_execution_id)
    )
    return ExecutionFill(CID, ExecutionFillId(fill_id), economic, external)


@pytest.mark.parametrize(
    "identity_type",
    [ClientOrderId, BrokerOrderId, BrokerExecutionId, ExecutionFillId],
)
def test_identities_normalize_validate_and_are_hashable(identity_type) -> None:
    raw = (
        " 12345678-1234-5678-1234-567812345678 "
        if identity_type is ClientOrderId
        else " external-id "
    )
    identity = identity_type(raw)
    assert identity.value == raw.strip()
    assert {identity: "found"}[identity_type(raw.strip())] == "found"
    with pytest.raises(ValueError):
        identity_type("  ")
    with pytest.raises(TypeError):
        identity_type(1)


def test_generated_client_order_ids_are_standard_and_distinct() -> None:
    first = create_execution_order(request(), T0)
    second = create_execution_order(request(), T0)
    assert first.client_order_id != second.client_order_id
    assert ClientOrderId(first.client_order_id.value) == first.client_order_id


def test_creation_has_stable_initial_values() -> None:
    order = created()
    assert order.client_order_id is CID
    assert order.state is ExecutionOrderState.CREATED
    assert order.cumulative_filled_quantity == 0
    assert order.remaining_quantity == 100
    assert order.version == 0
    assert order.broker_order_id is None


def test_risk_approval_does_not_implicitly_authorize() -> None:
    order = created()
    assert approved(order).status is RiskDecisionStatus.APPROVED
    assert order.state is ExecutionOrderState.CREATED
    with pytest.raises(ValueError):
        begin_submission(order, at(3))


def test_authorization_requires_approved_matching_risk_and_bindings() -> None:
    order = created()
    rejected = RiskDecision(
        RiskDecisionStatus.REJECTED,
        order.request,
        at(1),
        RiskRejectionReason.ORDER_QUANTITY_LIMIT_EXCEEDED,
    )
    with pytest.raises(ValueError, match="APPROVED"):
        authorize_execution_order(order, rejected, authorization(order))
    other_request = OrderRequest(SPY, OrderSide.BUY, 100, T0)
    mismatch = RiskDecision(RiskDecisionStatus.APPROVED, other_request, at(1))
    with pytest.raises(ValueError, match="bind"):
        authorize_execution_order(order, mismatch, authorization(order))
    with pytest.raises(ValueError, match="bind"):
        authorize_execution_order(
            order, approved(order), authorization(order, request_override=other_request)
        )


def test_authorization_and_submission_advance_immutable_versions() -> None:
    original = created()
    order = authorize_execution_order(original, approved(original), authorization(original))
    assert original.state is ExecutionOrderState.CREATED
    assert order.state is ExecutionOrderState.AUTHORIZED
    assert order.version == 1
    pending = begin_submission(order, at(3))
    assert pending.state is ExecutionOrderState.SUBMISSION_PENDING
    assert pending.version == 2


@pytest.mark.parametrize(
    "make_order",
    [
        lambda: begin_submission(authorized(), at(3)),
        lambda: record_submitted(begin_submission(authorized(), at(3)), at(4)),
        acknowledged,
        lambda: record_fill(acknowledged(), execution_fill("f1", 30))[0],
        lambda: record_fill(acknowledged(), execution_fill("f1", 100))[0],
        lambda: request_cancellation(acknowledged(), at(6)),
        lambda: record_cancelled(request_cancellation(acknowledged(), at(6)), at(7)),
        lambda: record_broker_rejection(
            begin_submission(authorized(), at(3)),
            BrokerRejection(CID, at(4), "x", "rejected"),
        ),
        lambda: record_submission_unknown(begin_submission(authorized(), at(3)), at(4)),
    ],
)
def test_begin_submission_rejects_every_non_authorized_state(make_order) -> None:
    with pytest.raises(ValueError):
        begin_submission(make_order(), at(10))


def test_submission_unknown_is_not_a_retryable_failure() -> None:
    pending = begin_submission(authorized(), at(3))
    unknown = record_submission_unknown(pending, at(4))
    assert unknown.state is ExecutionOrderState.UNKNOWN
    assert record_submission_unknown(unknown, at(5)) is unknown
    with pytest.raises(ValueError):
        begin_submission(unknown, at(6))


def test_submission_and_acknowledgement_replays_are_idempotent() -> None:
    pending = begin_submission(authorized(), at(3))
    submitted = record_submitted(pending, at(4))
    assert record_submitted(submitted, at(5)) is submitted
    ack = record_acknowledgement(submitted, BrokerOrderId("A"), at(5))
    assert record_acknowledgement(ack, BrokerOrderId("A"), at(6)) is ack
    with pytest.raises(ValueError, match="different"):
        record_acknowledgement(ack, BrokerOrderId("B"), at(6))


def test_repository_duplicate_add_and_optimistic_version() -> None:
    repository = InMemoryExecutionOrderRepository()
    order = created()
    repository.add(order)
    assert repository.get(CID) is order
    with pytest.raises(ValueError, match="already"):
        repository.add(order)
    next_order = authorize_execution_order(order, approved(order), authorization(order))
    with pytest.raises(ValueError, match="stale"):
        repository.save(next_order, expected_version=2)
    repository.save(next_order, expected_version=0)
    assert repository.get(CID) is next_order
    with pytest.raises(ValueError, match="exactly one"):
        repository.save(next_order, expected_version=1)


def test_partial_then_full_fill_and_accounting_gate() -> None:
    order = acknowledged()
    first = execution_fill("fill-1", 30, broker_execution_id="exec-1")
    order, accepted = record_fill(order, first)
    assert accepted
    assert order.state is ExecutionOrderState.PARTIALLY_FILLED
    assert order.cumulative_filled_quantity == 30
    assert order.remaining_quantity == 70
    replay, accepted = record_fill(order, first)
    assert replay is order
    assert not accepted
    order, accepted = record_fill(
        order, execution_fill("fill-2", 70, broker_execution_id="exec-2", minute=7)
    )
    assert accepted
    assert order.state is ExecutionOrderState.FILLED
    assert order.cumulative_filled_quantity == 100


def test_fill_identity_conflicts_wrong_contract_and_overfill_are_rejected() -> None:
    order = acknowledged()
    order, _ = record_fill(
        order, execution_fill("fill-1", 30, broker_execution_id="exec-1")
    )
    with pytest.raises(ValueError, match="identity"):
        record_fill(
            order, execution_fill("fill-2", 30, broker_execution_id="exec-1")
        )
    with pytest.raises(ValueError, match="instrument"):
        record_fill(order, execution_fill("fill-2", 1, instrument=SPY))
    with pytest.raises(ValueError, match="side"):
        record_fill(order, execution_fill("fill-2", 1, side=OrderSide.SELL))
    with pytest.raises(ValueError, match="exceed"):
        record_fill(order, execution_fill("fill-2", 71))


def test_late_fills_during_cancel_can_remain_partial_or_fill() -> None:
    order, _ = record_fill(acknowledged(), execution_fill("f1", 30))
    cancelling = request_cancellation(order, at(7))
    partial, accepted = record_fill(
        cancelling, execution_fill("f2", 20, minute=8)
    )
    assert accepted and partial.state is ExecutionOrderState.PARTIALLY_FILLED
    cancelling = request_cancellation(partial, at(9))
    filled, accepted = record_fill(
        cancelling, execution_fill("f3", 50, minute=10)
    )
    assert accepted and filled.state is ExecutionOrderState.FILLED


def test_cancellation_can_complete_or_become_unknown() -> None:
    cancelling = request_cancellation(acknowledged(), at(6))
    cancelled = record_cancelled(cancelling, at(7))
    assert cancelled.state is ExecutionOrderState.CANCELLED
    assert record_cancelled(cancelled, at(8)) is cancelled
    assert record_submission_unknown(cancelling, at(7)).state is ExecutionOrderState.UNKNOWN


def test_broker_rejection_is_separate_and_idempotent() -> None:
    pending = begin_submission(authorized(), at(3))
    rejection = BrokerRejection(CID, at(4), "201", "broker refused")
    rejected = record_broker_rejection(pending, rejection)
    assert rejected.state is ExecutionOrderState.REJECTED
    assert record_broker_rejection(rejected, rejection) is rejected
    assert not isinstance(rejection, RiskDecision)
    assert not isinstance(rejection, ExecutionRejection)


@pytest.mark.parametrize(
    ("state", "quantity"),
    [
        (ExecutionOrderState.ACKNOWLEDGED, 0),
        (ExecutionOrderState.PARTIALLY_FILLED, 30),
        (ExecutionOrderState.FILLED, 100),
    ],
)
def test_unknown_converges_from_broker_observations(state, quantity) -> None:
    unknown = record_submission_unknown(begin_submission(authorized(), at(3)), at(4))
    observation = BrokerOrderObservation(
        CID, state, at(5), BrokerOrderId("broker-1"), quantity
    )
    resolved = apply_broker_order_observation(unknown, observation)
    assert resolved.state is state
    assert resolved.cumulative_filled_quantity == quantity


def test_reconciliation_reports_unresolved_and_accepts_duplicate_observation() -> None:
    unknown = record_submission_unknown(begin_submission(authorized(), at(3)), at(4))
    result = reconcile_order(unknown, None)
    assert result.issues[0].kind is ReconciliationIssueKind.UNRESOLVED_SUBMISSION
    observation = BrokerOrderObservation(
        CID, ExecutionOrderState.ACKNOWLEDGED, at(5), BrokerOrderId("broker-1")
    )
    resolved = apply_broker_order_observation(unknown, observation)
    assert apply_broker_order_observation(resolved, observation) is resolved


def test_illegal_terminal_transitions_are_rejected() -> None:
    filled, _ = record_fill(acknowledged(), execution_fill("f1", 100))
    with pytest.raises(ValueError):
        request_cancellation(filled, at(7))
    cancelled = record_cancelled(request_cancellation(acknowledged(), at(6)), at(7))
    with pytest.raises(ValueError):
        record_fill(cancelled, execution_fill("late", 1, minute=8))


@pytest.mark.parametrize(
    "source",
    [
        lambda: begin_submission(authorized(), at(3)),
        lambda: record_submitted(begin_submission(authorized(), at(3)), at(4)),
        lambda: record_submission_unknown(begin_submission(authorized(), at(3)), at(4)),
    ],
)
def test_all_submission_rejection_sources_are_legal(source) -> None:
    rejection = BrokerRejection(CID, at(8), None, "broker refused")
    assert record_broker_rejection(source(), rejection).state is ExecutionOrderState.REJECTED


@pytest.mark.parametrize(
    "target",
    [
        ExecutionOrderState.SUBMITTED,
        ExecutionOrderState.REJECTED,
        ExecutionOrderState.CANCELLED,
    ],
)
def test_unknown_additional_recovery_paths(target) -> None:
    unknown = record_submission_unknown(begin_submission(authorized(), at(3)), at(4))
    observation = BrokerOrderObservation(CID, target, at(5))
    assert apply_broker_order_observation(unknown, observation).state is target
