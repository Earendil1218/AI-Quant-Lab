"""Neutral async rules without broker imports. / 不依赖 broker 的异步规则测试。"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from execution import (
    BrokerExecutionId, BrokerOrderId, BrokerOrderObservation, ClientOrderId, DispatchOperation,
    DispatchOutcome, DispatchResult, ExecutionFill, ExecutionFillId, ExecutionObservation,
    ExecutionOrderState as State, ObservationKind as Kind, SubmissionAuthorization,
    apply_broker_order_observation, apply_dispatch_result, apply_execution_observation,
    authorize_execution_order, begin_submission, create_execution_order, record_fill,
    record_submission_unknown, reconcile_order, ReconciliationIssueKind,
)
from risk import RiskDecision, RiskDecisionStatus
from trading import AssetClass, Fill, InstrumentId, OrderRequest, OrderSide


NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)


def pending():
    request = OrderRequest(InstrumentId(AssetClass.EQUITY, "NVDA"), OrderSide.BUY, 100, NOW)
    order = create_execution_order(request, NOW)
    authorization = SubmissionAuthorization(order.client_order_id, request, NOW, "operator:test")
    return begin_submission(authorize_execution_order(order,
        RiskDecision(RiskDecisionStatus.APPROVED, request, NOW), authorization), NOW)


def observation(order, kind, **kwargs):
    return ExecutionObservation(order.client_order_id, order.request, kind, NOW,
                                BrokerOrderId("broker"), **kwargs)


def test_explicit_rejection_can_precede_perm_identity():
    order = pending()
    obs = ExecutionObservation(order.client_order_id, order.request, Kind.REJECTED, NOW, detail="rejected")
    result = apply_execution_observation(order, obs, applied_at=NOW)
    assert result.order.state is State.REJECTED and result.order.broker_order_id is None
    assert apply_execution_observation(result.order, obs, applied_at=NOW).order is result.order


def test_connection_loss_moves_inflight_to_unknown_not_rejected():
    order = pending()
    ack = apply_execution_observation(order, observation(order, Kind.WORKING), applied_at=NOW).order
    result = apply_execution_observation(ack, observation(ack, Kind.CONNECTION_LOST), applied_at=NOW)
    assert result.order.state is State.UNKNOWN and result.unresolved
    assert result.order.broker_order_id == ack.broker_order_id
    assert apply_execution_observation(result.order, observation(ack, Kind.WORKING), applied_at=NOW).order.state is State.ACKNOWLEDGED


def test_foreign_client_request_and_identity_cannot_apply():
    order = pending()
    obs = observation(order, Kind.WORKING)
    for bad in (replace(obs, client_order_id=ClientOrderId("other")),
                replace(obs, request=replace(order.request, quantity=50))):
        with pytest.raises(ValueError):
            apply_execution_observation(order, bad, applied_at=NOW)
    ack = apply_execution_observation(order, obs, applied_at=NOW).order
    with pytest.raises(ValueError):
        apply_execution_observation(ack, replace(obs, broker_order_id=BrokerOrderId("other")), applied_at=NOW)


def test_no_callback_bypasses_created_or_authorized():
    order = pending()
    for state in (State.CREATED, State.AUTHORIZED):
        source = replace(order, state=state, authorization=None if state is State.CREATED else order.authorization)
        with pytest.raises(ValueError):
            apply_execution_observation(source, observation(order, Kind.WORKING), applied_at=NOW)


def test_legacy_reconciliation_quantity_is_not_double_booked():
    order = replace(record_submission_unknown(pending(), NOW), broker_order_id=BrokerOrderId("broker"))
    snapshot = BrokerOrderObservation(order.client_order_id, State.PARTIALLY_FILLED, NOW, BrokerOrderId("broker"), 30)
    legacy = apply_broker_order_observation(order, snapshot)
    fill = ExecutionFill(order.client_order_id, ExecutionFillId("f"),
                         Fill(order.request.instrument, order.request.side, 30, NOW, Decimal(100), Decimal(1)),
                         BrokerExecutionId("e"))
    assert legacy is order and legacy.cumulative_filled_quantity == 0
    updated, accepted = record_fill(legacy, fill)
    assert accepted and updated.cumulative_filled_quantity == 30
    assert apply_broker_order_observation(updated, snapshot) is updated


@pytest.mark.parametrize("quantity", [0, 30, 100])
def test_legacy_filled_snapshot_requires_complete_execution_evidence(quantity):
    order = record_submission_unknown(pending(), NOW)
    if quantity:
        fill = ExecutionFill(order.client_order_id, ExecutionFillId("f"),
            Fill(order.request.instrument, order.request.side, quantity, NOW, Decimal(100), Decimal(1)),
            BrokerExecutionId("e"))
        order, accepted = record_fill(order, fill)
        assert accepted
        # Simulate an unresolved stored lifecycle while retaining real accepted economic facts.
        order = replace(order, state=State.UNKNOWN)
    snapshot = BrokerOrderObservation(order.client_order_id, State.FILLED, NOW, BrokerOrderId("broker"), 100)
    result = apply_broker_order_observation(order, snapshot)
    assert result.state is (State.FILLED if quantity == 100 else State.UNKNOWN)
    assert result.cumulative_filled_quantity == quantity and result.fills == order.fills
    assert result.authorization == order.authorization and result.request == order.request
    issues = reconcile_order(result, snapshot).issues
    assert bool(issues) is (quantity != 100)
    if issues:
        assert issues[0].kind is ReconciliationIssueKind.FILL_QUANTITY_MISMATCH


@pytest.mark.parametrize("reported", [20, 50])
def test_legacy_snapshot_quantity_mismatch_is_evidence_only(reported):
    order = record_submission_unknown(pending(), NOW)
    fill = ExecutionFill(order.client_order_id, ExecutionFillId("f"),
        Fill(order.request.instrument, order.request.side, 30, NOW, Decimal(100), Decimal(1)),
        BrokerExecutionId("e"))
    order, _ = record_fill(order, fill)
    order = replace(order, state=State.UNKNOWN)
    snapshot = BrokerOrderObservation(order.client_order_id, State.PARTIALLY_FILLED, NOW, BrokerOrderId("broker"), reported)
    assert apply_broker_order_observation(order, snapshot) is order
    assert reconcile_order(order, snapshot).issues[0].kind is ReconciliationIssueKind.FILL_QUANTITY_MISMATCH


def test_unknown_dispatch_cannot_regress_terminal_and_rejects_foreign_result():
    order = pending()
    rejected = apply_execution_observation(order, observation(order, Kind.REJECTED, detail="rejected"), applied_at=NOW).order
    result = DispatchResult(order.client_order_id, DispatchOperation.SUBMIT, DispatchOutcome.DELIVERY_UNKNOWN, "uncertain")
    assert apply_dispatch_result(rejected, result, NOW) is rejected
    with pytest.raises(ValueError):
        apply_dispatch_result(order, replace(result, client_order_id=ClientOrderId("other")), NOW)


def test_observation_does_not_relax_time_monotonicity():
    order = pending()
    with pytest.raises(ValueError):
        apply_execution_observation(order, observation(order, Kind.WORKING), applied_at=NOW-timedelta(seconds=1))
