"""Regression proofs for B1-B4/M1-M2; no broker/network effects.

安全修复回归：临时数据库、真实 domain、fake transport。
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal, localcontext, Inexact, Rounded
from threading import Barrier

import pytest

from application import PaperRunner, StalePlanningDecision
from broker.ibkr.models import IBKROrderIdentity, OrderBinding, SessionEvent
from broker.ibkr.recovery import PersistentIdentityRegistry, PersistentIBKRInbox, BROKER_CODEC
from execution import ClientOrderId, SubmissionAuthorization, ExecutionOrderState as State
from infrastructure import SQLiteExecutionRepository, SQLiteAttemptClaims
from portfolio.sizing import FixedQuantitySizing
from risk import RiskConfiguration, ValuationContext
from tests.ibkr_fakes import NVDA, at, execution, commission, status, saved_pending
from tests.test_execution_persistence import setup, reopen
from tests.test_paper_runner import build
from trading import TargetExposureIntent


def planned(repo, runner):
    return runner.plan(TargetExposureIntent(NVDA, at(0), 1.0, "ma", "long"), FixedQuantitySizing(100),
                       RiskConfiguration(maximum_position_quantity=100),
                       ValuationContext(at(0), {NVDA: Decimal("100")}))


def authorize(ticket, identity, seconds=1):
    return SubmissionAuthorization(ClientOrderId(identity), ticket.plan.request, at(seconds), "operator:review")


def empty_runner(tmp_path):
    repo = SQLiteExecutionRepository(tmp_path / "execution.db")
    repo.initialize_accounting(Decimal("50000"))
    runner, fake = build(repo)
    return repo, runner, fake


def complete(repo, runner, fake, order):
    runner.dispatch(order.client_order_id, applied_at=at(3))
    inbox = PersistentIBKRInbox(repo, fake.generation, 3)
    inbox.append(execution())
    runner.consume_inbox(inbox, applied_at=at(7))
    inbox.append(commission())
    runner.consume_inbox(inbox, applied_at=at(9))
    runner.account_pending()


def test_stale_planning_rejected_after_fill(tmp_path):
    repo, runner, fake = empty_runner(tmp_path)
    first = planned(repo, runner)
    cached = planned(repo, runner)
    order = runner.prepare(first, authorize(first, "first"), prepared_at=at(2))
    complete(repo, runner, fake, order)
    restarted, _ = build(reopen(repo))
    with pytest.raises(StalePlanningDecision, match="stale"):
        restarted.prepare(cached, authorize(cached, "second"), prepared_at=at(10))
    assert repo.get(ClientOrderId("second")) is None
    assert repo.load_portfolio().quantity_for(NVDA) == 100
    assert len(fake.placed) == 1
    fresh = planned(repo, restarted)
    assert fresh.plan.request is None and fresh.risk_decision is None
    assert fresh.portfolio_revision != cached.portfolio_revision


def test_fresh_plan_and_risk_binding_cannot_be_swapped(tmp_path):
    repo, runner, _ = empty_runner(tmp_path)
    ticket = planned(repo, runner)
    changed = replace(ticket, risk_decision=replace(ticket.risk_decision, evaluated_at=at(1)))
    with pytest.raises(StalePlanningDecision, match="mismatched"):
        runner.prepare(changed, authorize(changed, "forged"), prepared_at=at(2))
    assert repo.get(ClientOrderId("forged")) is None
    pending = runner.prepare(ticket, authorize(ticket, "fresh"), prepared_at=at(2))
    assert pending.state is State.SUBMISSION_PENDING


def test_stale_risk_cannot_be_attached_to_new_revision(tmp_path):
    repo, runner, fake = empty_runner(tmp_path)
    old = planned(repo, runner)
    order = runner.prepare(old, authorize(old, "first"), prepared_at=at(2))
    complete(repo, runner, fake, order)
    fresh = planned(repo, runner)
    forged = replace(fresh, plan=old.plan, risk_decision=old.risk_decision)
    with pytest.raises(StalePlanningDecision):
        runner.prepare(forged, authorize(forged, "replayed-risk"), prepared_at=at(10))
    assert len(fake.placed) == 1


def test_freshness_rechecked_before_claim_after_preparation(tmp_path):
    repo, pending, fake, adapter, inbox = setup(tmp_path)
    # A separately accepted fill changes accounting while this prepared order waits.
    _, other = saved_pending(repo, cid="late-fill-owner")
    from execution import ExecutionObservation, ObservationKind, BrokerOrderId, BrokerExecutionId, ExecutionFillId, ExecutionFill
    from trading import Fill
    economic = Fill(NVDA, other.request.side, 1, at(4), Decimal("100"), Decimal("0"))
    fill = ExecutionFill(other.client_order_id, ExecutionFillId("other-fill"), economic, BrokerExecutionId("other-exec"))
    obs = ExecutionObservation(other.client_order_id, other.request, ObservationKind.FILL, at(5),
                               BrokerOrderId("other-broker"), execution_fill=fill)
    repo.apply_observation(obs, applied_at=at(5), expected_version=other.version)
    repo.account_pending()
    from execution import DispatchOperation
    with pytest.raises(StalePlanningDecision):
        SQLiteAttemptClaims(repo).claim(pending, DispatchOperation.SUBMIT)
    assert not fake.placed
    assert repo.list_recovery_candidates()[0].claimed_operations == ()


@pytest.mark.parametrize("state", [State.SUBMISSION_PENDING, State.ACKNOWLEDGED, State.UNKNOWN, State.PARTIALLY_FILLED])
def test_unfinished_execution_still_blocks_planning(tmp_path, state):
    repo, pending, _, adapter, _ = setup(tmp_path)
    if state is State.ACKNOWLEDGED:
        from tests.test_execution_persistence import ack
        repo.apply_observation(ack(pending), applied_at=at(5), expected_version=pending.version)
    elif state is State.UNKNOWN:
        from execution import record_submission_unknown
        repo.save(record_submission_unknown(pending, at(5)), pending.version)
    elif state is State.PARTIALLY_FILLED:
        adapter.submit(pending)
        inbox = PersistentIBKRInbox(repo, "offline-session", 3)
        inbox.append(commission()); inbox.append(execution(shares=40))
        PaperRunner(repo, adapter).consume_inbox(inbox, applied_at=at(9))
        repo.account_pending()
    runner, _ = build(reopen(repo))
    with pytest.raises(ValueError):
        planned(repo, runner)


def test_real_callback_float_quantities_persist_and_replay(tmp_path):
    repo, pending, _, adapter, inbox = setup(tmp_path)
    adapter.submit(pending)
    inbox.append(status(filled=0.0, remaining=100.0))
    inbox.append(execution(shares=100.0))
    inbox.append(commission())
    values = tuple(BROKER_CODEC.loads(text) for text in repo.inbox(inbox.namespace))
    assert type(values[0].filled) is int and type(values[0].remaining) is int
    assert type(values[1].shares) is int and values[1].shares == 100
    fresh = reopen(repo)
    runner, _ = build(fresh)
    runner.consume_inbox(PersistentIBKRInbox(fresh, "offline-session", 3), applied_at=at(9))
    assert runner.account_pending().quantity_for(NVDA) == 100


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 0.5, 100.5, True])
@pytest.mark.parametrize("kind", ["execution", "status"])
def test_invalid_or_fractional_raw_quantity_fails_without_truncation(tmp_path, value, kind):
    repo, _, _, _, inbox = setup(tmp_path)
    event = execution(shares=value) if kind == "execution" else status(filled=value)
    with pytest.raises(ValueError):
        inbox.append(event)
    assert repo.pending_inbox_count() == 0


def binding(order, *, generation="session", order_id=41, perm_id=9001, account="DU_TEST"):
    return OrderBinding(IBKROrderIdentity(account, 3, order_id, generation, order.client_order_id, perm_id),
                        order.request, 123)


@pytest.mark.parametrize("identity", ["api", "permanent"])
def test_two_registry_identity_conflict(tmp_path, identity):
    repo = SQLiteExecutionRepository(tmp_path / "db.sqlite")
    _, a = saved_pending(repo, cid="A")
    _, b = saved_pending(repo, cid="B")
    one = PersistentIdentityRegistry(repo, "session")
    two = PersistentIdentityRegistry(reopen(repo), "session")
    one.register(binding(a))
    bad = binding(b, perm_id=9002) if identity == "api" else binding(b, order_id=42)
    with pytest.raises(ValueError, match="identity"):
        two.register(bad)
    assert len(repo.evidence("ibkr-bindings:session")) == 1
    assert len(PersistentIdentityRegistry(reopen(repo), "session").bindings()) == 1


def test_concurrent_independent_registry_identity_conflict(tmp_path):
    repo = SQLiteExecutionRepository(tmp_path / "db.sqlite")
    orders = [saved_pending(repo, cid=name)[1] for name in ("A", "B")]
    registries = [PersistentIdentityRegistry(reopen(repo), "session") for _ in orders]
    barrier = Barrier(2)
    def register(index):
        barrier.wait()
        try:
            registries[index].register(binding(orders[index]))
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(register, range(2))) == 1
    assert len(PersistentIdentityRegistry(reopen(repo), "session").bindings()) == 1


def test_identity_idempotence_forward_conflict_and_session_scope(tmp_path):
    repo = SQLiteExecutionRepository(tmp_path / "db.sqlite")
    _, order = saved_pending(repo)
    original = binding(order)
    first = PersistentIdentityRegistry(repo, "session")
    first.register(original)
    second = PersistentIdentityRegistry(reopen(repo), "session")
    second.register(original)
    with pytest.raises(ValueError):
        second.register(binding(order, order_id=42))
    new = PersistentIdentityRegistry(repo, "new-session")
    with pytest.raises(ValueError):
        new.register(binding(order, generation="new-session", perm_id=9999))
    new.register(binding(order, generation="new-session", order_id=55))
    assert new.get(order.client_order_id).identity.perm_id == 9001


def test_permanent_identity_scope_allows_distinct_accounts(tmp_path):
    repo = SQLiteExecutionRepository(tmp_path / "db.sqlite")
    _, a = saved_pending(repo, cid="A")
    _, b = saved_pending(repo, cid="B")
    registry = PersistentIdentityRegistry(repo, "session")
    registry.register(binding(a))
    registry.register(binding(b, account="DU_OTHER", order_id=42))
    assert len(PersistentIdentityRegistry(reopen(repo), "session").bindings()) == 2


def test_old_internal_schema_is_rejected_without_migration(tmp_path):
    repo = SQLiteExecutionRepository(tmp_path / "db.sqlite")
    with repo._transaction() as db:
        db.execute("PRAGMA user_version=1")
    with pytest.raises(ValueError, match="database version"):
        reopen(repo)


def test_correction_family_rejected_across_session_restart(tmp_path):
    repo, pending, _, adapter, inbox = setup(tmp_path)
    adapter.submit(pending)
    inbox.append(commission()); inbox.append(execution(shares=40))
    runner = PaperRunner(repo, adapter)
    runner.consume_inbox(inbox, applied_at=at(9))
    before = runner.account_pending()
    original = repo.get(pending.client_order_id)
    fresh = reopen(repo)
    old = PersistentIdentityRegistry(fresh, "offline-session").get(pending.client_order_id)
    registry = PersistentIdentityRegistry(fresh, "new-session")
    registry.register(replace(old, identity=replace(old.identity, session_generation="new-session")))
    later = PersistentIBKRInbox(fresh, "new-session", 3)
    later.append(commission("tradeA.02", generation="new-session", observed_at=at(11)))
    later.append(execution("tradeA.02", shares=40, generation="new-session", observed_at=at(12)))
    with pytest.raises(ValueError, match="CORRECTION_REQUIRES_RECONCILIATION"):
        later.replay()
    after = fresh.account_pending()
    assert fresh.get(pending.client_order_id) == original
    assert after.cash == before.cash and dict(after.quantities) == dict(before.quantities)
    assert sum(f.fill.commission for f in original.fills) == Decimal("1")
    assert fresh.pending_inbox_count() == 2


def test_execution_then_commission_resolves_only_correlated_wait(tmp_path):
    repo, pending, fake, adapter, inbox = setup(tmp_path)
    runner = PaperRunner(repo, adapter)
    runner.dispatch(pending.client_order_id, applied_at=at(3))
    inbox.append(execution())
    runner.consume_inbox(inbox, applied_at=at(7))
    assert len(repo.unresolved_observations()) == 1
    fresh = reopen(repo)
    inbox = PersistentIBKRInbox(fresh, fake.generation, 3)
    inbox.append(commission())
    restarted, _ = build(fresh)
    restarted.consume_inbox(inbox, applied_at=at(9))
    restarted.account_pending()
    assert restarted.recover() == ((), (), 0, 0)
    assert planned(fresh, restarted).plan.request is None
    with fresh._transaction() as db:
        row = db.execute("SELECT unresolved,resolved_at,resolved_by FROM observations WHERE reason='WAITING_FOR_COMMISSION'").fetchone()
    assert row[0] == 1 and row[1] == at(9).isoformat() and row[2]


@pytest.mark.parametrize("source", ["connection_lost", "delivery_unknown"])
def test_fill_pairing_never_clears_true_uncertainty(tmp_path, source):
    repo, pending, fake, adapter, inbox = setup(tmp_path)
    runner = PaperRunner(repo, adapter)
    if source == "delivery_unknown":
        fake.place_error = TimeoutError("possibly delivered")
    runner.dispatch(pending.client_order_id, applied_at=at(3))
    if source == "connection_lost":
        inbox.append(SessionEvent(fake.generation, at(4), "disconnected"))
    inbox.append(execution())
    runner.consume_inbox(inbox, applied_at=at(7))
    inbox.append(commission())
    runner.consume_inbox(inbox, applied_at=at(9))
    runner.account_pending()
    fresh = reopen(repo)
    assert fresh.unresolved_observations()
    restarted, _ = build(fresh)
    with pytest.raises(ValueError, match="unresolved"):
        planned(fresh, restarted)


def test_accounting_independent_of_ambient_decimal_context(tmp_path):
    repo, pending, _, adapter, inbox = setup(tmp_path)
    adapter.submit(pending)
    inbox.append(commission(value="0.123456789"))
    inbox.append(execution(price=Decimal("100.123456789")))
    obs = inbox.replay()[-1]
    repo.apply_observation(obs, applied_at=at(9), expected_version=pending.version)
    with localcontext() as context:
        context.prec = 6
        low = repo.account_pending()
        revision_low = repo.planning_snapshot()[1]
    normal = reopen(repo).load_portfolio()
    assert low.cash == normal.cash == Decimal("9987.530864311")
    assert dict(low.quantities) == dict(normal.quantities)
    assert revision_low == repo.planning_snapshot()[1]


def test_accounting_precision_loss_fails_without_markers(tmp_path):
    repo, pending, _, adapter, inbox = setup(tmp_path)
    adapter.submit(pending)
    inbox.append(commission(value="0"))
    inbox.append(execution(price=Decimal("100." + "1" * 60)))
    repo.apply_observation(inbox.replay()[-1], applied_at=at(9), expected_version=pending.version)
    with pytest.raises((Inexact, Rounded)):
        repo.account_pending()
    assert reopen(repo).pending_accounting_count() == 1
    assert repo.load_portfolio().cash == Decimal("20000")
