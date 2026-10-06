"""Durable boundaries with fresh repository instances after injected failures.

临时数据库与真实 domain；验证重启结果而不只验证异常。
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from threading import Barrier

import pytest

from application import PaperRunner
from broker.ibkr import IBKRPaperAdapter, EquityContractSpec
from broker.ibkr.recovery import PersistentIdentityRegistry, PersistentIBKRInbox
from execution import (
    BrokerOrderId, DispatchOperation, DispatchOutcome, ExecutionOrderState as State,
    ExecutionObservation, ObservationKind, RecoveryAction, apply_execution_observation,
    record_submission_unknown, request_cancellation, ClientOrderId, SubmissionAuthorization,
)
from infrastructure import SQLiteAttemptClaims, SQLiteExecutionRepository
from infrastructure.codec import Codec
from infrastructure.sqlite_execution import VersionConflict
from tests.ibkr_fakes import CONFIG, NVDA, FakeTransport, at, saved_pending, status, execution, commission
from portfolio.sizing import FixedQuantitySizing
from risk import RiskConfiguration, ValuationContext
from trading import TargetExposureIntent


def setup(tmp_path):
    repo = SQLiteExecutionRepository(tmp_path / "execution.db")
    repo.initialize_accounting(Decimal("20000"))
    fake = FakeTransport()
    registry = PersistentIdentityRegistry(repo, fake.generation)
    adapter = IBKRPaperAdapter(CONFIG, EquityContractSpec(NVDA), fake, SQLiteAttemptClaims(repo), registry)
    runner = PaperRunner(repo, adapter)
    ticket = runner.plan(TargetExposureIntent(NVDA, at(0), 1.0, "ma", "long"), FixedQuantitySizing(100),
                         RiskConfiguration(), ValuationContext(at(0), {NVDA: Decimal("100")}))
    pending = runner.prepare(ticket, SubmissionAuthorization(ClientOrderId("local-logical-order"),
                             ticket.plan.request, at(1), "operator:test"), prepared_at=at(2))
    inbox = PersistentIBKRInbox(repo, fake.generation, CONFIG.client_id)
    return repo, pending, fake, adapter, inbox


def reopen(repo):
    return SQLiteExecutionRepository(repo.path)


def ack(pending):
    return ExecutionObservation(pending.client_order_id, pending.request, ObservationKind.WORKING,
                                at(5), BrokerOrderId("ibkr:7:DU_TEST:perm:9001"), 0)


def test_roundtrip_authority_identity_times_and_versions(tmp_path):
    repo, pending, _, _, _ = setup(tmp_path)
    assert reopen(repo).get(pending.client_order_id) == pending
    result = repo.apply_observation(ack(pending), applied_at=at(9), expected_version=pending.version)
    actual = reopen(repo).get(pending.client_order_id)
    assert actual == result.order
    assert actual.broker_order_id == ack(pending).broker_order_id
    assert actual.version == pending.version + 1 and actual.state is State.ACKNOWLEDGED
    assert actual.created_at.utcoffset().total_seconds() == 0


def test_stale_reader_cannot_overwrite_committed_state(tmp_path):
    repo, pending, _, _, _ = setup(tmp_path)
    other = reopen(repo)
    stale = other.get(pending.client_order_id)
    repo.apply_observation(ack(pending), applied_at=at(9), expected_version=pending.version)
    with pytest.raises(VersionConflict):
        other.save(record_submission_unknown(stale, at(10)), stale.version)
    assert other.get(pending.client_order_id).state is State.ACKNOWLEDGED


def test_claim_is_durable_and_has_no_retry_after_reopen(tmp_path):
    repo, pending, _, _, _ = setup(tmp_path)
    SQLiteAttemptClaims(repo).claim(pending, DispatchOperation.SUBMIT)
    fresh = reopen(repo)
    with pytest.raises(ValueError, match="already claimed"):
        SQLiteAttemptClaims(fresh).claim(pending, DispatchOperation.SUBMIT)
    candidate, = fresh.list_recovery_candidates()
    assert candidate.action is RecoveryAction.RECONCILIATION_REQUIRED
    assert candidate.claimed_operations == ("submit",)


def test_concurrent_claim_uses_database_uniqueness(tmp_path):
    repo, pending, _, _, _ = setup(tmp_path)
    barrier = Barrier(6)
    def attempt(_):
        claims = SQLiteAttemptClaims(reopen(repo))
        barrier.wait()
        try:
            claims.claim(pending, DispatchOperation.SUBMIT)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(pool.map(attempt, range(6))) == 1


@pytest.mark.parametrize("window", ["before_claim", "after_claim", "after_transport"])
def test_crash_windows_preserve_send_safety(tmp_path, window):
    repo, pending, fake, adapter, _ = setup(tmp_path)
    class Crash(BaseException):
        pass
    def crash(*args):
        raise Crash()
    if window == "before_claim":
        fake.on_qualify = crash
    elif window == "after_claim":
        fake.next_order_id = crash
    else:
        fake.on_place = crash
    with pytest.raises(Crash):
        adapter.submit(pending)
    fresh = reopen(repo)
    new_fake = FakeTransport()
    new_adapter = IBKRPaperAdapter(CONFIG, EquityContractSpec(NVDA), new_fake,
                                  SQLiteAttemptClaims(fresh), PersistentIdentityRegistry(fresh, new_fake.generation))
    candidate, = fresh.list_recovery_candidates()
    if window == "before_claim":
        assert candidate.action is RecoveryAction.ATTEMPT_ALLOWED
        assert new_adapter.submit(candidate.order).outcome is DispatchOutcome.DISPATCH_RETURNED
        assert len(new_fake.placed) == 1
    else:
        assert candidate.action is RecoveryAction.RECONCILIATION_REQUIRED
        with pytest.raises(ValueError, match="claimed"):
            new_adapter.submit(candidate.order)
        assert new_fake.placed == []
    assert len(fake.placed) == (1 if window == "after_transport" else 0)


def test_uncertain_delivery_restores_unknown_without_resend(tmp_path):
    repo, pending, fake, adapter, _ = setup(tmp_path)
    fake.place_error = TimeoutError("possibly received")
    runner = PaperRunner(repo, adapter)
    assert runner.dispatch(pending.client_order_id, applied_at=at(9)).outcome is DispatchOutcome.DELIVERY_UNKNOWN
    fresh = reopen(repo)
    assert fresh.get(pending.client_order_id).state is State.UNKNOWN
    with pytest.raises(ValueError, match="recovery"):
        runner.dispatch(pending.client_order_id, applied_at=at(10))
    assert len(fake.placed) == 1


def test_ack_before_crash_preserves_state_and_blocks_new_submission(tmp_path):
    repo, pending, fake, adapter, _ = setup(tmp_path)
    adapter.submit(pending)
    repo.apply_observation(ack(pending), applied_at=at(9), expected_version=pending.version)
    fresh = reopen(repo)
    candidate, = fresh.list_recovery_candidates()
    assert candidate.order.state is State.ACKNOWLEDGED
    assert candidate.order.version == 3
    assert candidate.action is RecoveryAction.RECONCILIATION_REQUIRED
    with pytest.raises(ValueError):
        SQLiteAttemptClaims(fresh).claim(candidate.order, DispatchOperation.SUBMIT)


def paired(repo, adapter, inbox, pending):
    adapter.submit(pending)
    inbox.append(execution())
    inbox.append(commission())
    return inbox.replay()[-1]


def test_execution_accounting_gap_and_restart_replay(tmp_path):
    repo, pending, _, adapter, inbox = setup(tmp_path)
    fill = paired(repo, adapter, inbox, pending)
    result = repo.apply_observation(fill, applied_at=at(9), expected_version=pending.version)
    assert result.fill_accepted
    assert repo.pending_accounting_count() == 1
    assert repo.load_portfolio().cash == Decimal("20000")
    # Crash after execution commit, before accounting; reconstruct a new store.
    fresh = reopen(repo)
    state = fresh.account_pending()
    assert state.cash == Decimal("9999") and state.quantity_for(NVDA) == 100
    again = reopen(repo)
    current = again.get(pending.client_order_id)
    assert not again.apply_observation(fill, applied_at=at(10), expected_version=current.version).fill_accepted
    assert again.get(pending.client_order_id) == current
    state = again.account_pending()
    assert state.cash == Decimal("9999") and state.quantity_for(NVDA) == 100
    assert again.pending_accounting_count() == 0
    assert type(current.fills[0].fill.price) is Decimal


@pytest.mark.parametrize("first", ["execution", "commission"])
def test_unpaired_raw_callback_survives_restart(tmp_path, first):
    repo, pending, _, adapter, inbox = setup(tmp_path)
    adapter.submit(pending)
    initial, later = (execution(), commission()) if first == "execution" else (commission(), execution())
    inbox.append(initial)
    fresh = reopen(repo)
    recovered = PersistentIBKRInbox(fresh, "offline-session", 3)
    recovered.append(later)
    fill = recovered.replay()[-1]
    assert fill.kind is ObservationKind.FILL
    fresh.apply_observation(fill, applied_at=at(9), expected_version=pending.version)
    fresh.account_pending()
    recovered.append(initial)
    recovered.append(later)
    for obs in recovered.replay():
        if obs.kind is ObservationKind.FILL:
            current = fresh.get(pending.client_order_id)
            assert not fresh.apply_observation(obs, applied_at=at(10), expected_version=current.version).fill_accepted
    assert fresh.account_pending().cash == Decimal("9999")


def test_transaction_rolls_back_quantity_and_dedup_on_failure(tmp_path, monkeypatch):
    repo, pending, _, adapter, inbox = setup(tmp_path)
    obs = paired(repo, adapter, inbox, pending)
    original = repo._persist_fills
    def fail(db, order):
        original(db, order)
        raise RuntimeError("failure after dedup insertion before commit")
    monkeypatch.setattr(repo, "_persist_fills", fail)
    with pytest.raises(RuntimeError):
        repo.apply_observation(obs, applied_at=at(9), expected_version=pending.version)
    fresh = reopen(repo)
    assert fresh.get(pending.client_order_id) == pending
    assert fresh.pending_accounting_count() == 0
    assert fresh.apply_observation(obs, applied_at=at(10), expected_version=pending.version).fill_accepted


def test_accounting_failure_rolls_back_markers(tmp_path):
    repo, pending, _, adapter, inbox = setup(tmp_path)
    obs = paired(repo, adapter, inbox, pending)
    repo.apply_observation(obs, applied_at=at(9), expected_version=pending.version)
    # SQL trigger injects a failure at the accounting commit boundary.
    with repo._transaction() as db:
        db.execute("CREATE TRIGGER fail_accounting BEFORE INSERT ON accounting BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(Exception, match="injected"):
        repo.account_pending()
    fresh = reopen(repo)
    assert fresh.pending_accounting_count() == 1
    assert fresh.load_portfolio().cash == Decimal("20000")
    with fresh._transaction() as db:
        db.execute("DROP TRIGGER fail_accounting")
    assert fresh.account_pending().cash == Decimal("9999")


def test_conflicting_fill_after_restart_is_not_silently_accepted(tmp_path):
    repo, pending, _, adapter, inbox = setup(tmp_path)
    obs = paired(repo, adapter, inbox, pending)
    repo.apply_observation(obs, applied_at=at(9), expected_version=pending.version)
    fresh = reopen(repo)
    current = fresh.get(pending.client_order_id)
    changed = replace(obs, execution_fill=replace(obs.execution_fill,
                       fill=replace(obs.execution_fill.fill, commission=Decimal("2"))))
    with pytest.raises(ValueError, match="identity"):
        fresh.apply_observation(changed, applied_at=at(10), expected_version=current.version)
    assert fresh.get(current.client_order_id) == current


def test_raw_conflict_remains_durable_and_blocks_replay(tmp_path):
    repo, pending, _, adapter, inbox = setup(tmp_path)
    paired(repo, adapter, inbox, pending)
    inbox.append(commission(value="2"))
    recovered = PersistentIBKRInbox(reopen(repo), "offline-session", 3)
    with pytest.raises(ValueError, match="conflicts"):
        recovered.replay()
    assert reopen(repo).pending_inbox_count() == 3


def test_cancel_claim_persists_separately_from_submit(tmp_path):
    repo, pending, _, adapter, inbox = setup(tmp_path)
    adapter.submit(pending)
    inbox.append(status())
    observed, = inbox.replay()
    acknowledged = repo.apply_observation(observed, applied_at=at(9), expected_version=pending.version).order
    cancelling = request_cancellation(acknowledged, at(10))
    repo.save(cancelling, acknowledged.version)
    # registry used by adapter must observe the durable permId before cancellation.
    adapter.registry = PersistentIdentityRegistry(repo, "offline-session")
    assert adapter.cancel(cancelling).outcome is DispatchOutcome.DISPATCH_RETURNED
    fresh = reopen(repo)
    with pytest.raises(ValueError, match="claimed"):
        SQLiteAttemptClaims(fresh).claim(cancelling, DispatchOperation.CANCEL)
    assert fresh.list_recovery_candidates()[0].claimed_operations == ("cancel", "submit")


@pytest.mark.parametrize("bad", [1.0, float("nan"), Decimal("NaN"), Decimal("Infinity")])
def test_codec_rejects_unsafe_numeric_values(bad):
    with pytest.raises((TypeError, ValueError)):
        Codec().dumps(bad)


def test_initial_balance_cannot_reset_after_restart(tmp_path):
    repo, _, _, _, _ = setup(tmp_path)
    fresh = reopen(repo)
    fresh.initialize_accounting(Decimal("20000.00"))
    with pytest.raises(ValueError, match="already bound"):
        fresh.initialize_accounting(Decimal("30000"))


def test_stale_snapshot_claim_fails_without_consuming(tmp_path):
    repo, pending, _, _, _ = setup(tmp_path)
    claims = SQLiteAttemptClaims(repo)
    with pytest.raises(ValueError, match="current saved"):
        claims.claim(replace(pending, version=8), DispatchOperation.SUBMIT)
    claims.claim(pending, DispatchOperation.SUBMIT)
    claims.verify_current(pending, DispatchOperation.SUBMIT)


def test_invalid_schema_version_is_rejected(tmp_path):
    repo, _, _, _, _ = setup(tmp_path)
    with repo._transaction() as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError, match="database version"):
        reopen(repo)


def test_concurrent_durable_adapters_enter_transport_once(tmp_path):
    repo, pending, fake, adapter, _ = setup(tmp_path)
    barrier = Barrier(4)
    fake.on_qualify = barrier.wait
    adapters = [IBKRPaperAdapter(CONFIG, EquityContractSpec(NVDA), fake,
                SQLiteAttemptClaims(reopen(repo)), adapter.registry) for _ in range(4)]
    def send(index):
        try:
            return adapters[index].submit(pending).outcome
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(send, range(4)))
    assert results.count(DispatchOutcome.DISPATCH_RETURNED) == 1
    assert len(fake.placed) == 1
    assert reopen(repo).list_recovery_candidates()[0].claimed_operations == ("submit",)


def test_stale_registry_cannot_overwrite_persisted_perm_identity(tmp_path):
    repo, pending, fake, adapter, inbox = setup(tmp_path)
    adapter.submit(pending)
    stale = PersistentIdentityRegistry(reopen(repo), fake.generation)
    initial = stale.get(pending.client_order_id)
    inbox.append(status())
    inbox.replay()
    with pytest.raises(VersionConflict, match="evidence"):
        stale.register(initial)
    current = PersistentIdentityRegistry(reopen(repo), fake.generation).get(pending.client_order_id)
    assert current.identity.perm_id == 9001


def test_exact_decimal_and_naive_timestamp_roundtrip():
    codec = Codec()
    _, order = saved_pending()
    naive = replace(order, created_at=order.created_at.replace(tzinfo=None),
                    updated_at=order.updated_at.replace(tzinfo=None))
    assert codec.loads(codec.dumps(naive)) == naive
    amount = Decimal("123456789.123456789000000001")
    assert codec.loads(codec.dumps(amount)).as_tuple() == amount.as_tuple()


def test_dedup_identity_cannot_be_reused_for_another_order(tmp_path):
    repo, pending, _, adapter, inbox = setup(tmp_path)
    obs = paired(repo, adapter, inbox, pending)
    repo.apply_observation(obs, applied_at=at(9), expected_version=pending.version)
    _, other = saved_pending(repo, cid="another-order")
    cloned_fill = replace(obs.execution_fill, client_order_id=other.client_order_id)
    changed = replace(obs, client_order_id=other.client_order_id, request=other.request, execution_fill=cloned_fill)
    with pytest.raises(ValueError, match="identity conflict"):
        repo.apply_observation(changed, applied_at=at(10), expected_version=other.version)
    assert reopen(repo).get(other.client_order_id) == other
    assert repo.pending_accounting_count() == 1


def test_fills_cannot_be_removed_by_later_snapshot(tmp_path):
    repo, pending, _, adapter, inbox = setup(tmp_path)
    obs = paired(repo, adapter, inbox, pending)
    filled = repo.apply_observation(obs, applied_at=at(9), expected_version=pending.version).order
    forged = replace(filled, state=State.UNKNOWN, version=filled.version + 1,
                     fills=(), cumulative_filled_quantity=0)
    with pytest.raises(ValueError, match="immutable"):
        repo.save(forged, filled.version)
    assert reopen(repo).get(filled.client_order_id) == filled
