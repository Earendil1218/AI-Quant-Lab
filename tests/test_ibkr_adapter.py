"""Real execution domain with a fake external transport. / 真实执行 domain 配合假外部 transport。"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from broker.ibkr import IBKRPaperAdapter
from execution import (
    DispatchOperation, DispatchOutcome, ExecutionOrderState as State, apply_dispatch_result,
    apply_execution_observation, begin_submission, request_cancellation,
)
from tests.ibkr_fakes import at, setup_adapter, status


def test_saved_pending_dispatch_returns_without_mutating_aggregate():
    repo, pending, fake, adapter, normalizer = setup_adapter()
    result = adapter.submit(pending)
    assert result.outcome is DispatchOutcome.DISPATCH_RETURNED
    assert repo.get(pending.client_order_id) == pending
    assert apply_dispatch_result(pending, result, at(9)) is pending
    assert len(fake.placed) == 1
    assert pending.state is State.SUBMISSION_PENDING
    obs, = normalizer.normalize(status())
    ack = apply_execution_observation(pending, obs, applied_at=at(9)).order
    assert ack.state is State.ACKNOWLEDGED
    assert ack.version == pending.version + 1
    repo.save(ack, pending.version)


def test_unpersisted_and_wrong_state_do_not_send():
    repo, pending, fake, adapter, _ = setup_adapter()
    with pytest.raises(ValueError, match="saved"):
        adapter.submit(replace(pending, version=pending.version + 1))
    with pytest.raises(ValueError, match="pending"):
        adapter.submit(replace(pending, state=State.AUTHORIZED))
    with pytest.raises(ValueError, match="pending"):
        adapter.submit(replace(pending, state=State.CREATED, authorization=None))
    assert not fake.placed


def test_local_save_failure_prevents_broker_call(monkeypatch):
    repo, pending, fake, adapter, _ = setup_adapter()
    authorized = replace(pending, state=State.AUTHORIZED, version=pending.version - 1)
    # Simulate a repository which still contains the pre-transition snapshot.
    monkeypatch.setattr(repo, "get", lambda cid: authorized)
    unsaved = begin_submission(authorized, at(3))
    def fail_save(*args, **kwargs):
        raise OSError("save failed")
    monkeypatch.setattr(repo, "save", fail_save)
    with pytest.raises(OSError):
        repo.save(unsaved, authorized.version)
    with pytest.raises(ValueError):
        adapter.submit(unsaved)
    assert not fake.placed


def test_multiple_adapter_instances_concurrently_enter_side_effect_once():
    _, pending, fake, first, _ = setup_adapter()
    second = IBKRPaperAdapter(first.config, first.spec, fake, first.claims, first.registry)
    barrier = Barrier(8)
    fake.on_qualify = barrier.wait
    def submit(index):
        try:
            return (first if index % 2 else second).submit(pending).outcome
        except ValueError:
            return "already claimed"
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(submit, range(8)))
    assert outcomes.count(DispatchOutcome.DISPATCH_RETURNED) == 1
    assert outcomes.count("already claimed") == 7
    assert len(fake.placed) == 1
    assert fake.counter == 41


def test_reentrant_submit_is_rejected_before_second_send():
    _, pending, fake, adapter, _ = setup_adapter()
    def callback():
        with pytest.raises(ValueError, match="claimed"):
            adapter.submit(pending)
    fake.on_place = callback
    adapter.submit(pending)
    assert len(fake.placed) == 1


def test_possible_delivery_becomes_unknown_and_claim_cannot_be_retried():
    _, pending, fake, adapter, _ = setup_adapter()
    fake.place_error = ConnectionError("lost after send")
    result = adapter.submit(pending)
    assert result.outcome is DispatchOutcome.DELIVERY_UNKNOWN
    unknown = apply_dispatch_result(pending, result, at(9))
    assert unknown.state is State.UNKNOWN
    with pytest.raises(ValueError):
        adapter.submit(pending)
    with pytest.raises(ValueError):
        adapter.submit(unknown)
    assert len(fake.placed) == 1


def test_known_disconnection_before_send_returns_not_sent():
    _, pending, fake, adapter, _ = setup_adapter()
    fake.session = replace(fake.session, connected=False)
    assert adapter.submit(pending).outcome is DispatchOutcome.NOT_SENT
    assert not fake.placed


def test_disconnect_during_qualification_is_checked_again():
    _, pending, fake, adapter, _ = setup_adapter()
    fake.on_qualify = lambda: setattr(fake, "session", replace(fake.session, connected=False))
    assert adapter.submit(pending).outcome is DispatchOutcome.NOT_SENT
    assert not fake.placed
    fake.session = replace(fake.session, connected=True)
    fake.on_qualify = None
    assert adapter.submit(pending).outcome is DispatchOutcome.DISPATCH_RETURNED
    assert len(fake.placed) == 1


def test_saved_snapshot_changed_during_preparation_does_not_send():
    repo, pending, fake, adapter, _ = setup_adapter()
    def change_state():
        repo.save(replace(pending, state=State.UNKNOWN, version=pending.version + 1), pending.version)
    fake.on_qualify = change_state
    assert adapter.submit(pending).outcome is DispatchOutcome.NOT_SENT
    assert not fake.placed
    assert fake.counter == 40
    # Revalidation sees a fresh saved version; the logical operation was never consumed.
    current = repo.get(pending.client_order_id)
    fresh = replace(current, state=State.SUBMISSION_PENDING, version=current.version + 1)
    repo.save(fresh, current.version)
    adapter.claims.validate(fresh, DispatchOperation.SUBMIT)
    fake.on_qualify = None
    assert adapter.submit(fresh).outcome is DispatchOutcome.DISPATCH_RETURNED


@pytest.mark.parametrize("cancel_error", [None, TimeoutError("cancel delivery unknown")])
def test_saved_cancellation_waits_for_broker_confirmation(cancel_error):
    repo, pending, fake, adapter, normalizer = setup_adapter()
    adapter.submit(pending)
    obs, = normalizer.normalize(status())
    ack = apply_execution_observation(pending, obs, applied_at=at(9)).order
    repo.save(ack, pending.version)
    cancelling = request_cancellation(ack, at(10))
    with pytest.raises(ValueError, match="saved"):
        adapter.cancel(cancelling)
    repo.save(cancelling, ack.version)
    fake.cancel_error = cancel_error
    result = adapter.cancel(cancelling)
    expected = DispatchOutcome.DELIVERY_UNKNOWN if cancel_error else DispatchOutcome.DISPATCH_RETURNED
    assert result.outcome is expected
    assert repo.get(pending.client_order_id).state is State.CANCEL_PENDING
    with pytest.raises(ValueError, match="claimed"):
        adapter.cancel(cancelling)
    assert len(fake.cancelled) == 1
    assert fake.cancelled[0].orderId == 41 and fake.cancelled[0].permId == 9001


@pytest.mark.parametrize("invalid", ["empty", "multiple", "wrong_contract"])
def test_qualification_failure_never_enters_order_transport(invalid):
    _, pending, fake, adapter, _ = setup_adapter()
    original = fake.qualify
    def qualify(contract):
        result = original(contract)
        if invalid == "empty":
            return ()
        if invalid == "multiple":
            return result + result
        contract.symbol = "WRONG"
        return result
    fake.qualify = qualify
    with pytest.raises(ValueError):
        adapter.submit(pending)
    assert not fake.placed
    assert fake.counter == 40
    adapter.claims.validate(pending, DispatchOperation.SUBMIT)
    fake.qualify = original
    assert adapter.submit(pending).outcome is DispatchOutcome.DISPATCH_RETURNED
    assert len(fake.placed) == 1 and fake.counter == 41
    with pytest.raises(ValueError, match="claimed"):
        adapter.submit(pending)


@pytest.mark.parametrize("step", ["map_contract", "prepare_order"])
def test_mapping_preparation_failure_does_not_consume_claim(monkeypatch, step):
    import broker.ibkr.adapter as module
    _, pending, fake, adapter, _ = setup_adapter()
    original = getattr(module, step)
    def fail(*args):
        raise ValueError("preparation failed")
    monkeypatch.setattr(module, step, fail)
    with pytest.raises(ValueError, match="preparation"):
        adapter.submit(pending)
    assert not fake.placed and fake.counter == 40
    adapter.claims.validate(pending, DispatchOperation.SUBMIT)
    monkeypatch.setattr(module, step, original)
    assert adapter.submit(pending).outcome is DispatchOutcome.DISPATCH_RETURNED
    assert len(fake.placed) == 1 and fake.counter == 41


def test_cancellation_claim_is_shared_under_concurrency():
    repo, pending, fake, adapter, normalizer = setup_adapter()
    adapter.submit(pending)
    obs, = normalizer.normalize(status())
    ack = apply_execution_observation(pending, obs, applied_at=at(9)).order
    repo.save(ack, pending.version)
    cancelling = request_cancellation(ack, at(10))
    repo.save(cancelling, ack.version)
    other = IBKRPaperAdapter(adapter.config, adapter.spec, fake, adapter.claims, adapter.registry)
    barrier = Barrier(2)
    def cancel(instance):
        barrier.wait()
        try:
            return instance.cancel(cancelling).outcome
        except ValueError:
            return "already claimed"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(cancel, (adapter, other)))
    assert outcomes.count(DispatchOutcome.DISPATCH_RETURNED) == 1
    assert len(fake.cancelled) == 1
