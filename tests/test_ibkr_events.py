"""Asynchronous broker facts, delayed fees and race semantics. / 异步事实、延迟费用和竞态。"""

from dataclasses import replace
from decimal import Decimal

import pytest

from broker.ibkr.models import ErrorEvent, EventSource, SessionEvent
from execution import (
    BrokerOrderId, BrokerOrderObservation, DispatchOperation, DispatchOutcome, DispatchResult,
    ExecutionOrderState as State, ObservationKind as Kind,
    apply_broker_order_observation, apply_dispatch_result, apply_execution_observation, request_cancellation,
    record_submission_unknown,
)
from tests.ibkr_fakes import at, commission, execution, setup_adapter, status


def dispatched():
    repo, pending, fake, adapter, normalizer = setup_adapter()
    adapter.submit(pending)
    return pending, normalizer


def apply(order, observation, second=20):
    return apply_execution_observation(order, observation, applied_at=at(second))


@pytest.mark.parametrize("raw,kind", [
    ("ApiPending", Kind.PENDING), ("PendingSubmit", Kind.PENDING),
    ("PreSubmitted", Kind.HELD), ("Submitted", Kind.WORKING),
    ("Filled", Kind.COMPLETION), ("PendingCancel", Kind.CANCEL_PENDING),
    ("Cancelled", Kind.CANCELLED), ("ApiCancelled", Kind.CANCELLED),
    ("Inactive", Kind.UNRESOLVED), ("FutureStatus", Kind.UNRESOLVED),
])
def test_status_mapping_is_not_a_direct_state_cast(raw, kind):
    pending, normalizer = dispatched()
    obs, = normalizer.normalize(status(raw, 100 if raw == "Filled" else 0, 0 if raw == "Filled" else 100))
    assert obs.kind is kind
    result = apply(pending, obs)
    assert result.order.cumulative_filled_quantity == 0 and result.order.fills == ()
    if kind in {Kind.COMPLETION, Kind.UNRESOLVED, Kind.HELD, Kind.PENDING}:
        assert result.unresolved and result.order is pending


def test_synthetic_status_never_confirms_cancellation():
    pending, normalizer = dispatched()
    obs, = normalizer.normalize(status("Cancelled", source=EventSource.LOCAL))
    assert obs.kind is Kind.INFORMATION
    assert apply(pending, obs).order is pending


def test_duplicate_and_delayed_ack_dont_regress_filled_order():
    pending, normalizer = dispatched()
    ack, = normalizer.normalize(status())
    order = apply(pending, ack).order
    assert apply(order, ack).order is order
    normalizer.normalize(execution())
    fill, = normalizer.normalize(commission())
    filled = apply(order, fill).order
    assert filled.state is State.FILLED
    assert apply(filled, ack).order is filled
    assert apply(filled, fill).order is filled


def test_broker_completion_before_commission_never_double_counts():
    pending, normalizer = dispatched()
    completion, = normalizer.normalize(status("Filled", 100, 0))
    unresolved = apply(pending, completion)
    assert unresolved.unresolved and unresolved.order.cumulative_filled_quantity == 0
    execution_pending, = normalizer.normalize(execution())
    assert apply(pending, execution_pending).unresolved
    fill, = normalizer.normalize(commission())
    result = apply(pending, fill)
    assert result.fill_accepted and result.order.cumulative_filled_quantity == 100
    assert len(result.order.fills) == 1
    assert not apply(result.order, fill).fill_accepted


def test_legacy_filled_snapshot_then_execution_and_snapshot_replay():
    pending, normalizer = dispatched()
    order = record_submission_unknown(pending, at(3))
    normalizer.normalize(status())
    bid = normalizer.registry.get(order.client_order_id).identity.broker_order_id
    snapshot = BrokerOrderObservation(order.client_order_id, State.FILLED, at(5), bid, 100)
    unresolved = apply_broker_order_observation(order, snapshot)
    assert unresolved is order and unresolved.state is State.UNKNOWN
    assert unresolved.cumulative_filled_quantity == 0 and unresolved.fills == ()
    awaiting, = normalizer.normalize(execution())
    assert apply(unresolved, awaiting).unresolved
    fill, = normalizer.normalize(commission())
    result = apply(unresolved, fill)
    assert result.fill_accepted and result.order.state is State.FILLED
    assert result.order.cumulative_filled_quantity == 100 and len(result.order.fills) == 1
    assert apply_broker_order_observation(result.order, snapshot) is result.order


@pytest.mark.parametrize("uncertainty", ["session_loss", "delivery_unknown"])
def test_unknown_preserves_all_known_partial_fill_facts(uncertainty):
    pending, normalizer = dispatched()
    ack, = normalizer.normalize(status())
    order = apply(pending, ack).order
    normalizer.normalize(execution(shares=30))
    fill, = normalizer.normalize(commission())
    partial = apply(order, fill).order
    assert partial.state is State.PARTIALLY_FILLED and partial.cumulative_filled_quantity == 30
    if uncertainty == "session_loss":
        lost, = normalizer.normalize(SessionEvent(normalizer.generation, at(21), "disconnected"))
        result = apply(partial, lost, 22)
        assert result.unresolved
        unknown = result.order
    else:
        result = DispatchResult(partial.client_order_id, DispatchOperation.SUBMIT,
                                DispatchOutcome.DELIVERY_UNKNOWN, "uncertain delivery")
        unknown = apply_dispatch_result(partial, result, at(22))
    assert unknown.state is State.UNKNOWN and unknown.cumulative_filled_quantity == 30
    assert unknown.fills == partial.fills
    assert unknown.fills[0].broker_execution_id == fill.execution_fill.broker_execution_id
    assert unknown.fills[0].broker_execution_id is not None
    assert unknown.broker_order_id == partial.broker_order_id
    assert unknown.authorization == partial.authorization
    assert unknown.request == partial.request and unknown.client_order_id == partial.client_order_id


def test_duplicate_commission_has_one_economic_acceptance():
    pending, normalizer = dispatched()
    awaiting, = normalizer.normalize(execution())
    assert awaiting.kind is Kind.EXECUTION_PENDING
    assert apply(pending, awaiting).order.cumulative_filled_quantity == 0
    first, = normalizer.normalize(commission())
    result = apply(pending, first)
    assert result.fill_accepted and result.order.cumulative_filled_quantity == 100
    replay, = normalizer.normalize(commission(observed_at=at(15)))
    assert replay.execution_fill.fill_id == first.execution_fill.fill_id
    assert replay.execution_fill == first.execution_fill
    repeated = apply(result.order, replay)
    assert not repeated.fill_accepted and repeated.order is result.order
    assert repeated.order.cumulative_filled_quantity == 100 and len(repeated.order.fills) == 1
    with pytest.raises(ValueError, match="conflict"):
        normalizer.normalize(commission(value="2"))


def test_cancelled_zero_then_late_partial_duplicate_and_full_fill():
    pending, normalizer = dispatched()
    ack, = normalizer.normalize(status())
    cancelling = request_cancellation(apply(pending, ack).order, at(21))
    cancelled, = normalizer.normalize(status("Cancelled", 0, 0))
    order = apply(cancelling, cancelled, 22).order
    assert order.state is State.CANCELLED and order.cumulative_filled_quantity == 0
    normalizer.normalize(execution(shares=30))
    first, = normalizer.normalize(commission())
    result = apply(order, first, 23)
    assert result.fill_accepted
    partial = result.order
    assert partial.state is State.CANCELLED and partial.cumulative_filled_quantity == 30
    duplicate = apply(partial, first, 24)
    assert not duplicate.fill_accepted and duplicate.order is partial
    with pytest.raises(ValueError, match="identity"):
        apply(partial, replace(first, broker_order_id=BrokerOrderId("wrong")), 24)
    conflict = replace(first, execution_fill=replace(first.execution_fill,
                       fill=replace(first.execution_fill.fill, price=Decimal("101"))))
    with pytest.raises(ValueError, match="different fill data"):
        apply(partial, conflict, 24)
    normalizer.normalize(execution("excess.01", 71))
    excess, = normalizer.normalize(commission("excess.01"))
    with pytest.raises(ValueError, match="exceed"):
        apply(partial, excess, 24)
    normalizer.normalize(execution("tradeB.01", 70))
    last, = normalizer.normalize(commission("tradeB.01"))
    filled = apply(partial, last, 25)
    assert filled.fill_accepted and filled.order.state is State.FILLED
    assert filled.order.cumulative_filled_quantity == 100 and len(filled.order.fills) == 2


def test_commission_before_execution_and_receipt_time_separation():
    pending, normalizer = dispatched()
    assert normalizer.normalize(commission(observed_at=at(6))) == ()
    fill, = normalizer.normalize(execution(execution_time=at(1), observed_at=at(9)))
    result = apply(pending, fill, second=30)
    assert result.order.updated_at == at(30)
    assert result.order.fills[0].fill.filled_at == at(1)
    with pytest.raises(ValueError, match="applied_at"):
        apply(result.order, fill, second=29)


def test_multiple_partial_executions_and_duplicate_callbacks():
    pending, normalizer = dispatched()
    order = pending
    for exec_id, shares in (("tradeA.01", 30), ("tradeB.01", 20), ("tradeC.01", 50)):
        normalizer.normalize(execution(exec_id, shares))
        fill, = normalizer.normalize(commission(exec_id))
        result = apply(order, fill)
        assert result.fill_accepted
        order = result.order
        replay, = normalizer.normalize(execution(exec_id, shares, observed_at=at(10)))
        assert apply(order, replay).order is order
    assert order.state is State.FILLED
    assert order.cumulative_filled_quantity == 100
    assert sum(f.fill.commission for f in order.fills) == Decimal("3")


def test_replayed_execution_in_fresh_normalizer_retains_fill_identity():
    from broker.ibkr.events import IBKREventNormalizer
    pending, first = dispatched()
    first.normalize(execution())
    original, = first.normalize(commission())
    second = IBKREventNormalizer(first.registry, first.generation, first.client_id)
    second.normalize(execution(observed_at=at(15)))
    replay, = second.normalize(commission(observed_at=at(16)))
    assert original.execution_fill == replay.execution_fill
    filled = apply(pending, original).order
    assert not apply(filled, replay).fill_accepted


@pytest.mark.parametrize("changes", [
    {"account": "U_LIVE"}, {"client_id": 4}, {"order_id": 42}, {"perm_id": 9002},
    {"con_id": 999}, {"symbol": "SPY"}, {"sec_type": "OPT"}, {"currency": "EUR"},
    {"side": "SLD"}, {"shares": 101}, {"shares": 0}, {"price": Decimal("NaN")},
    {"generation": "stale"},
])
def test_wrong_execution_context_is_rejected(changes):
    _, normalizer = dispatched()
    normalizer.normalize(status())
    with pytest.raises((ValueError, KeyError)):
        normalizer.normalize(execution(**changes))


def test_overfill_conflict_and_correction_are_not_silently_accepted():
    pending, normalizer = dispatched()
    normalizer.normalize(execution(shares=60))
    first, = normalizer.normalize(commission())
    partial = apply(pending, first).order
    with pytest.raises(ValueError, match="conflict"):
        normalizer.normalize(execution(shares=59))
    with pytest.raises(ValueError, match="correction"):
        normalizer.normalize(execution("tradeA.02", 60))
    normalizer.normalize(execution("tradeB.01", 50))
    second, = normalizer.normalize(commission("tradeB.01"))
    with pytest.raises(ValueError, match="exceed"):
        apply(partial, second)


@pytest.mark.parametrize("value,currency", [("NaN", "USD"), ("Infinity", "USD"),
    ("-1", "USD"), ("1.7976931348623157E+308", "USD"), ("1", "EUR")])
def test_invalid_or_missing_commission_is_not_zero(value, currency):
    _, normalizer = dispatched()
    normalizer.normalize(execution())
    with pytest.raises(ValueError, match="commission"):
        normalizer.normalize(commission(value=value, currency=currency))


def test_explicit_zero_commission_and_conflicting_revision():
    _, normalizer = dispatched()
    normalizer.normalize(execution())
    fill, = normalizer.normalize(commission(value="0"))
    assert fill.execution_fill.fill.commission == 0
    with pytest.raises(ValueError, match="conflict"):
        normalizer.normalize(commission(value="1"))


def test_partial_fill_preserves_cancel_then_late_fill_after_cancellation():
    pending, normalizer = dispatched()
    ack, = normalizer.normalize(status())
    order = apply(pending, ack).order
    order = request_cancellation(order, at(21))
    normalizer.normalize(execution(shares=30))
    first, = normalizer.normalize(commission())
    order = apply(order, first, 22).order
    assert order.state is State.CANCEL_PENDING and order.cumulative_filled_quantity == 30
    cancelled, = normalizer.normalize(status("Cancelled", 50, 0, observed_at=at(23)))
    result = apply(order, cancelled, 24)
    assert result.unresolved
    order = result.order
    assert order.state is State.CANCELLED
    normalizer.normalize(execution("tradeB.01", 20, observed_at=at(25)))
    late, = normalizer.normalize(commission("tradeB.01", observed_at=at(26)))
    order = apply(order, late, 27).order
    assert order.state is State.CANCELLED and order.cumulative_filled_quantity == 50
    assert not apply(order, late, 28).fill_accepted


def test_full_fill_wins_cancel_race():
    pending, normalizer = dispatched()
    ack, = normalizer.normalize(status())
    cancelling = request_cancellation(apply(pending, ack).order, at(21))
    normalizer.normalize(execution())
    fill, = normalizer.normalize(commission())
    filled = apply(cancelling, fill, 22).order
    cancelled, = normalizer.normalize(status("Cancelled", 100, 0))
    assert apply(filled, cancelled, 23).order is filled


def test_wrong_broker_identity_rejected_even_for_terminal_replay():
    pending, normalizer = dispatched()
    normalizer.normalize(execution())
    fill, = normalizer.normalize(commission())
    filled = apply(pending, fill).order
    with pytest.raises(ValueError, match="identity"):
        apply(filled, replace(fill, broker_order_id=BrokerOrderId("wrong")))


@pytest.mark.parametrize("code,kind", [(201, Kind.REJECTED), (200, Kind.UNRESOLVED),
    (1100, Kind.CONNECTION_LOST), (2104, Kind.INFORMATION), (10147, Kind.UNRESOLVED),
    (999999, Kind.UNRESOLVED), (202, Kind.CANCELLED)])
def test_errors_are_contextual_not_blanket_rejections(code, kind):
    pending, normalizer = dispatched()
    normalizer.normalize(status("PendingSubmit"))
    observation, = normalizer.normalize(ErrorEvent(normalizer.generation, 41, code, "reason", at(8)))
    assert observation.kind is kind
    result = apply(pending, observation)
    if kind is Kind.REJECTED:
        assert result.order.state is State.REJECTED
    elif kind in {Kind.UNRESOLVED, Kind.INFORMATION, Kind.CONNECTION_LOST}:
        assert result.order.state is not State.REJECTED


def test_unrelated_error_and_session_loss_do_not_reject():
    pending, normalizer = dispatched()
    assert normalizer.normalize(ErrorEvent(normalizer.generation, 999, 201, "other request", at(8))) == ()
    unresolved, = normalizer.normalize(SessionEvent(normalizer.generation, at(8), "disconnected"))
    assert apply(pending, unresolved).unresolved


def test_integral_ibkr_float_shares_are_exactly_converted():
    pending, normalizer = dispatched()
    normalizer.normalize(execution(shares=100.0))
    fill, = normalizer.normalize(commission())
    assert type(fill.execution_fill.fill.quantity) is int
    assert apply(pending, fill).order.state is State.FILLED


def test_invalid_execution_and_synthetic_status_do_not_poison_perm_binding():
    pending, normalizer = dispatched()
    with pytest.raises(ValueError):
        normalizer.normalize(execution(perm_id=999, symbol="WRONG"))
    normalizer.normalize(status("Cancelled", perm_id=999, source=EventSource.LOCAL))
    assert normalizer.registry.get(pending.client_order_id).identity.perm_id == 0
    normalizer.normalize(execution())
    assert normalizer.registry.get(pending.client_order_id).identity.perm_id == 9001


def test_open_order_validates_full_account_request_before_binding():
    from broker.ibkr.models import OpenOrderEvent
    pending, normalizer = dispatched()
    event = OpenOrderEvent(normalizer.generation, "DU_TEST", 3, 41, 9001, 123,
                            "NVDA", "STK", "USD", "BUY", 100, "MKT",
                            pending.client_order_id.value, "Submitted", at(5))
    for changes in ({"account": "OTHER"}, {"order_ref": "OTHER"}, {"side": "SELL"},
                    {"quantity": 99}, {"con_id": 999}, {"order_type": "LMT"}):
        with pytest.raises(ValueError):
            normalizer.normalize(replace(event, **changes))
        assert normalizer.registry.get(pending.client_order_id).identity.perm_id == 0
    obs, = normalizer.normalize(event)
    assert apply(pending, obs).order.state is State.ACKNOWLEDGED
