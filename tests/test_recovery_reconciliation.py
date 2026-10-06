"""Pure conservative recovery and reconciliation decisions. / 保守恢复与核对。"""

from dataclasses import replace

import pytest

from execution import (
    BrokerOrderId, BrokerOrderObservation, ExecutionOrderState as State,
    ReconciliationDecision as D, assess_reconciliation, RecoveryAction, classify_recovery,
)
from tests.ibkr_fakes import at, saved_pending


@pytest.mark.parametrize("local,broker,quantity,decision", [
    (State.SUBMISSION_PENDING, State.ACKNOWLEDGED, 0, D.ACKNOWLEDGEMENT_AVAILABLE),
    (State.ACKNOWLEDGED, State.PARTIALLY_FILLED, 20, D.ECONOMIC_EVIDENCE_REQUIRED),
    (State.PARTIALLY_FILLED, State.FILLED, 100, D.ECONOMIC_EVIDENCE_REQUIRED),
    (State.ACKNOWLEDGED, State.UNKNOWN, 0, D.UNKNOWN),
    (State.UNKNOWN, State.UNKNOWN, 0, D.UNKNOWN),
    (State.UNKNOWN, State.ACKNOWLEDGED, 0, D.ACKNOWLEDGEMENT_AVAILABLE),
    (State.ACKNOWLEDGED, State.ACKNOWLEDGED, 0, D.CONSISTENT),
    (State.CANCELLED, State.ACKNOWLEDGED, 0, D.CONFLICT),
])
def test_reconciliation_does_not_invent_economics(local, broker, quantity, decision):
    _, order = saved_pending()
    bid = BrokerOrderId("broker-1")
    order = replace(order, state=local, broker_order_id=bid,
                    cumulative_filled_quantity=10 if local is State.PARTIALLY_FILLED else 0)
    observation = BrokerOrderObservation(order.client_order_id, broker, at(9), bid, quantity)
    assert assess_reconciliation(order, observation).decision is decision
    assert order.state is local


@pytest.mark.parametrize("local", [State.UNKNOWN, State.SUBMISSION_PENDING, State.ACKNOWLEDGED])
def test_missing_never_authorizes_resend(local):
    _, pending = saved_pending()
    assert assess_reconciliation(replace(pending, state=local), None).decision is D.MISSING


def test_old_broker_observation_cannot_regress_local_state():
    _, pending = saved_pending()
    order = replace(pending, state=State.ACKNOWLEDGED, updated_at=at(20), broker_order_id=BrokerOrderId("b"))
    observation = BrokerOrderObservation(order.client_order_id, State.SUBMITTED, at(5), order.broker_order_id)
    assert assess_reconciliation(order, observation).decision is D.STALE


@pytest.mark.parametrize("conflict", ["identity", "overfill"])
def test_snapshot_conflicts_are_explicit(conflict):
    _, pending = saved_pending()
    order = replace(pending, broker_order_id=BrokerOrderId("b"))
    observation = BrokerOrderObservation(order.client_order_id, State.ACKNOWLEDGED, at(9),
                                        BrokerOrderId("wrong" if conflict == "identity" else "b"),
                                        101 if conflict == "overfill" else 0)
    assert assess_reconciliation(order, observation).decision is D.CONFLICT


def test_recovery_does_not_mutate_pending_or_clear_claim():
    _, pending = saved_pending()
    assert classify_recovery(pending, ()).action is RecoveryAction.ATTEMPT_ALLOWED
    assert classify_recovery(pending, ("submit",)).action is RecoveryAction.RECONCILIATION_REQUIRED
    assert pending.state is State.SUBMISSION_PENDING
