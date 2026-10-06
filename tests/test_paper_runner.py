"""Minimal orchestration and durable ingestion gates. / 最小编排与持久化接收门禁。"""

from dataclasses import replace
from decimal import Decimal

import pytest

from application import PaperRunner
from broker.ibkr import IBKRPaperAdapter, EquityContractSpec
from broker.ibkr.recovery import PersistentIdentityRegistry, PersistentIBKRInbox
from broker.ibkr.transport import ReadOnlyIBKRTransport
from execution import (
    ClientOrderId, DispatchOperation, ExecutionOrderState as State, ExecutionObservation, ObservationKind,
    SubmissionAuthorization, InMemoryAttemptClaims,
)
from infrastructure import SQLiteAttemptClaims, SQLiteExecutionRepository
from portfolio.sizing import FixedQuantitySizing
from risk import RiskConfiguration, ValuationContext
from tests.ibkr_fakes import CONFIG, NVDA, FakeTransport, at, status, execution, commission
from tests.test_execution_persistence import setup, reopen, ack
from trading import TargetExposureIntent


def build(repo, fake=None):
    fake = FakeTransport() if fake is None else fake
    adapter = IBKRPaperAdapter(CONFIG, EquityContractSpec(NVDA), fake, SQLiteAttemptClaims(repo),
                              PersistentIdentityRegistry(repo, fake.generation))
    return PaperRunner(repo, adapter), fake


def test_plan_authorize_dispatch_ingest_account_and_restart(tmp_path):
    repo = SQLiteExecutionRepository(tmp_path / "execution.db")
    repo.initialize_accounting(Decimal("20000"))
    runner, fake = build(repo)
    intent = TargetExposureIntent(NVDA, at(0), 1.0, "moving_average", "long")
    config = RiskConfiguration(maximum_order_quantity=100)
    valuation = ValuationContext(at(0), {NVDA: Decimal("100")})
    ticket = runner.plan(intent, FixedQuantitySizing(100), config, valuation)
    auth = SubmissionAuthorization(ClientOrderId("runner-order"), ticket.plan.request, at(1), "operator:offline-test")
    pending = runner.prepare(ticket, auth, prepared_at=at(2))
    runner.dispatch(pending.client_order_id, applied_at=at(3))
    assert len(fake.placed) == 1
    inbox = PersistentIBKRInbox(repo, fake.generation, 3)
    inbox.append(status())
    runner.consume_inbox(inbox, applied_at=at(5))
    assert repo.get(pending.client_order_id).state is State.ACKNOWLEDGED
    # Commission first permits a complete fill without an unresolved execution gap.
    inbox.append(commission(observed_at=at(6)))
    inbox.append(execution(observed_at=at(7)))
    runner.consume_inbox(inbox, applied_at=at(8))
    assert repo.get(pending.client_order_id).state is State.FILLED
    with pytest.raises(ValueError, match="accounting"):
        runner.plan(intent, FixedQuantitySizing(100), config, valuation)
    assert runner.account_pending().cash == Decimal("9999")
    restarted, _ = build(reopen(repo))
    assert restarted.recover() == ((), (), 0, 0)
    ticket = restarted.plan(intent, FixedQuantitySizing(100), config, valuation)
    assert ticket.plan.request is None and ticket.risk_decision is None


def test_inbox_crash_before_lifecycle_persistence_is_replayable(tmp_path):
    repo, pending, fake, adapter, inbox = setup(tmp_path)
    adapter.submit(pending)
    inbox.append(commission())
    inbox.append(execution())
    # No consumption; restart after raw callback persistence.
    fresh = reopen(repo)
    runner, _ = build(fresh)
    assert runner.recover()[3] == 2
    recovered = PersistentIBKRInbox(fresh, fake.generation, 3)
    runner.consume_inbox(recovered, applied_at=at(9))
    assert fresh.pending_inbox_count() == 0
    assert runner.account_pending().cash == Decimal("9999")


def test_crash_after_observations_before_inbox_ack_replays_safely(tmp_path, monkeypatch):
    repo, pending, fake, adapter, inbox = setup(tmp_path)
    adapter.submit(pending)
    inbox.append(commission())
    inbox.append(execution())
    runner = PaperRunner(repo, adapter)
    def crash(*args):
        raise RuntimeError("before inbox acknowledgement")
    monkeypatch.setattr(repo, "mark_inbox_consumed", crash)
    with pytest.raises(RuntimeError):
        runner.consume_inbox(inbox, applied_at=at(9))
    fresh = reopen(repo)
    assert fresh.get(pending.client_order_id).state is State.FILLED
    recovered, _ = build(fresh)
    recovered.consume_inbox(PersistentIBKRInbox(fresh, fake.generation, 3), applied_at=at(10))
    assert recovered.account_pending().cash == Decimal("9999")
    assert fresh.pending_accounting_count() == fresh.pending_inbox_count() == 0


def test_old_ack_replay_cannot_resolve_newer_unknown(tmp_path):
    repo, pending, _, _, _ = setup(tmp_path)
    acknowledged = repo.apply_observation(ack(pending), applied_at=at(5), expected_version=pending.version).order
    loss = ExecutionObservation(pending.client_order_id, pending.request, ObservationKind.CONNECTION_LOST, at(10))
    unknown = repo.apply_observation(loss, applied_at=at(10), expected_version=acknowledged.version).order
    fresh = reopen(repo)
    result = fresh.apply_observation(ack(pending), applied_at=at(11), expected_version=unknown.version)
    assert result.order == unknown
    assert fresh.unresolved_observations() == (loss,)


def test_unseen_stale_ack_retained_without_resolving_unknown(tmp_path):
    repo, pending, _, _, _ = setup(tmp_path)
    loss = ExecutionObservation(pending.client_order_id, pending.request, ObservationKind.CONNECTION_LOST, at(10))
    unknown = repo.apply_observation(loss, applied_at=at(10), expected_version=pending.version).order
    result = repo.apply_observation(ack(pending), applied_at=at(11), expected_version=unknown.version)
    assert result.order == unknown and result.unresolved
    assert len(reopen(repo).unresolved_observations()) == 2


def test_unresolved_latch_survives_later_ack_and_restart(tmp_path):
    repo, pending, _, adapter, _ = setup(tmp_path)
    unresolved = ExecutionObservation(pending.client_order_id, pending.request, ObservationKind.UNRESOLVED, at(3))
    repo.apply_observation(unresolved, applied_at=at(3), expected_version=pending.version)
    repo.apply_observation(ack(pending), applied_at=at(5), expected_version=pending.version)
    runner, _ = build(reopen(repo))
    with pytest.raises(ValueError, match="unresolved"):
        runner.dispatch(pending.client_order_id, applied_at=at(9))


def test_runner_rejects_memory_claim_composition(tmp_path):
    repo, _, _, adapter, _ = setup(tmp_path)
    adapter.claims = InMemoryAttemptClaims(repo)
    with pytest.raises(ValueError, match="persistent"):
        PaperRunner(repo, adapter)


def test_real_transport_remains_locked_with_sqlite_claims(tmp_path):
    repo, pending, _, _, _ = setup(tmp_path)
    transport = ReadOnlyIBKRTransport(CONFIG)
    # No connection is opened; production transport must refuse order operations.
    with pytest.raises(ValueError, match="locked"):
        transport.preflight()
    assert SQLiteAttemptClaims(repo).validate(pending, DispatchOperation.SUBMIT) is None


def test_pending_raw_input_blocks_new_planning_even_without_execution(tmp_path):
    repo = SQLiteExecutionRepository(tmp_path / "execution.db")
    repo.initialize_accounting(Decimal("20000"))
    runner, _ = build(repo)
    inbox = PersistentIBKRInbox(repo, "offline-session", 3)
    inbox.append(commission())
    runner.consume_inbox(inbox, applied_at=at(9))
    assert repo.pending_inbox_count() == 1
    with pytest.raises(ValueError, match="unresolved"):
        runner.plan(None, None, None, None)
