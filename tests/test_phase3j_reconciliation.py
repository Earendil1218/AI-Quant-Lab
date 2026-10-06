"""Offline broker recovery against real durable execution state.

真实 SQLite、纯映射及 policy；只替换外部 session/query，禁止真实网络。
"""

from dataclasses import replace
from decimal import Decimal

import pytest

from application import PaperRunner
from broker.ibkr.config import PaperSafetyError
from broker.ibkr.models import OpenOrderEvent
from broker.ibkr.observation import RawBrokerSnapshot, map_snapshot, owned_identities
from broker.ibkr.session import PaperObservationSession, SessionState
from broker.ibkr.transport import ReadOnlyIBKRTransport, SessionEvidence
from execution.broker_state import MatchStatus as M, BrokerState, reconcile_snapshot
from infrastructure.reconciliation import ReconciliationStore, CODEC
from infrastructure.sqlite_execution import VersionConflict
from tests.ibkr_fakes import CONFIG, at, status, execution, commission
from tests.test_execution_persistence import setup, reopen
from tests.test_paper_runner import build


def raw(*, query="query-1", generation="offline-session", orders=True, complete=True, **changes):
    opened = OpenOrderEvent(generation, CONFIG.account, 3, 41, 9001, 123, "NVDA", "STK", "USD",
                            "BUY", 100.0, "MKT", "local-logical-order", "Submitted", at(10))
    value = RawBrokerSnapshot(query, generation, CONFIG.account, at(12),
                             (opened,) if orders else (),
                             (status(generation=generation, observed_at=at(10)),) if orders else (), (), complete)
    return replace(value, **changes)


class FakeSessionTransport:
    def __init__(self, snapshot):
        self.generation = snapshot.generation
        self.snapshot = snapshot
        self.connected = False
        self.queries = 0
        self.accounts = (CONFIG.account,)
        self.on_query = None

    def connect_readonly(self, *, integration_opt_in=False):
        self.connected = True

    def evidence(self):
        return SessionEvidence(self.generation, self.connected, CONFIG.host, CONFIG.port, 3, self.accounts)

    def query_snapshot(self):
        self.queries += 1
        if self.on_query:
            self.on_query()
        return self.snapshot

    def close(self):
        self.connected = False


def submitted(tmp_path, *, permanent=True):
    repo, pending, fake, adapter, inbox = setup(tmp_path)
    adapter.submit(pending)
    if permanent:
        adapter.registry.resolve(fake.generation, 3, 41, 9001, CONFIG.account)
    return repo, pending, fake, adapter, inbox


def assess(repo, snapshot):
    return ReconciliationStore(repo).reconcile(map_snapshot(snapshot), owned_identities)


def test_scenario_a_crash_before_callback_commit_matches_durable_identity(tmp_path):
    repo, pending, fake, _, _ = submitted(tmp_path)
    fresh = reopen(repo)
    runner, _ = build(fresh)
    session = PaperObservationSession(CONFIG, FakeSessionTransport(raw(generation="reconnected")))
    report = runner.reconcile_session(session)
    assert report.results[0].status is M.MATCHED
    assert session.state is SessionState.READY
    assert fresh.get(pending.client_order_id) == pending  # no synthetic acknowledgement
    assert len(fake.placed) == 1
    assert ReconciliationStore(reopen(repo)).reports() == (report,)
    with pytest.raises(ValueError):
        runner.dispatch(pending.client_order_id, applied_at=at(20))


def test_scenario_b_local_only_does_not_resend(tmp_path):
    repo, pending, fake, _, _ = submitted(tmp_path)
    report = assess(reopen(repo), raw(orders=False))
    assert report.results[0].status is M.LOCAL_ONLY
    assert ReconciliationStore(reopen(repo)).blocked()
    runner, _ = build(reopen(repo))
    with pytest.raises(ValueError, match="reconciliation"):
        runner.dispatch(pending.client_order_id, applied_at=at(20))
    assert len(fake.placed) == 1


def test_scenario_c_broker_only_never_adopted(tmp_path):
    repo, pending, _, _, _ = setup(tmp_path)
    report = assess(repo, raw())
    assert {r.status for r in report.results} == {M.BROKER_ONLY, M.LOCAL_ONLY}
    assert not repo.evidence("ibkr-bindings:offline-session")
    assert repo.get(pending.client_order_id) == pending


@pytest.mark.parametrize("field,value", [("symbol", "AAPL"), ("con_id", 124), ("side", "SELL"), ("quantity", 101)])
def test_scenario_d_strong_identity_with_field_conflict(tmp_path, field, value):
    repo, pending, _, _, _ = submitted(tmp_path)
    original = raw()
    if field == "quantity":
        original = replace(original, statuses=(replace(original.statuses[0], remaining=value),))
    report = assess(repo, replace(original, orders=(replace(original.orders[0], **{field: value}),)))
    assert report.results[0].status is M.CONFLICT
    assert repo.get(pending.client_order_id) == pending


def test_scenario_e_duplicate_callbacks_and_queries_are_idempotent(tmp_path):
    repo, _, _, _, _ = submitted(tmp_path)
    original = raw()
    duplicate = replace(original, orders=original.orders * 2, statuses=original.statuses * 2)
    first = assess(repo, duplicate)
    assert len(first.results) == 1
    assert assess(reopen(repo), duplicate) == first
    assess(reopen(repo), raw(query="new-query", generation="new-session", observed_at=at(13)))
    assert len(ReconciliationStore(repo).reports()) == 1
    assert repo.pending_accounting_count() == 0


def test_scenario_f_disconnect_reconnect_does_not_submit(tmp_path):
    repo, _, fake, _, _ = submitted(tmp_path)
    runner, _ = build(repo)
    transport = FakeSessionTransport(raw())
    session = PaperObservationSession(CONFIG, transport)
    runner.reconcile_session(session)
    assert session.state is SessionState.READY
    transport.connected = False
    assert session.state is SessionState.DEGRADED
    with pytest.raises(PaperSafetyError):
        session.connect()
    fresh = PaperObservationSession(CONFIG, FakeSessionTransport(raw(query="new", generation="new")))
    runner.reconcile_session(fresh)
    assert fresh.state is SessionState.READY
    assert len(fake.placed) == 1 and not fake.cancelled


@pytest.mark.parametrize("name", ["FutureStatus", "Inactive", ""])
def test_unknown_status_explicitly_blocks(tmp_path, name):
    repo, _, _, _, _ = submitted(tmp_path)
    original = raw()
    snapshot = replace(original, orders=(replace(original.orders[0], status=name),), statuses=())
    mapped = map_snapshot(snapshot)
    assert mapped.orders[0].state is BrokerState.UNKNOWN
    assert assess(repo, snapshot).results[0].status is M.UNKNOWN


def test_missing_status_quantities_are_not_fabricated(tmp_path):
    repo, _, _, _, _ = submitted(tmp_path)
    snapshot = raw(statuses=())
    assert map_snapshot(snapshot).orders[0].filled is None
    assert assess(repo, snapshot).results[0].status is M.UNKNOWN


def test_incomplete_query_never_proves_absence(tmp_path):
    repo, _, _, _, _ = submitted(tmp_path)
    report = assess(repo, raw(orders=False, complete=False))
    assert all(r.status is M.UNKNOWN for r in report.results)


def test_new_session_api_identity_without_perm_is_not_owned(tmp_path):
    repo, _, _, _, _ = submitted(tmp_path, permanent=False)
    report = assess(repo, raw(generation="new-session"))
    assert {r.status for r in report.results} == {M.BROKER_ONLY, M.LOCAL_ONLY}


def test_ambiguous_identity_rejected_by_pure_policy(tmp_path):
    from execution import ClientOrderId
    repo, _, _, _, _ = submitted(tmp_path)
    orders, payloads = ReconciliationStore(repo).inputs()
    owner = owned_identities(payloads)[0]
    report = reconcile_snapshot(map_snapshot(raw()), orders, (owner, replace(owner, local_id=ClientOrderId("other"))))
    assert report.results[0].status is M.CONFLICT


@pytest.mark.parametrize("field,value", [("quantity", 0.5), ("quantity", float("nan")),
    ("quantity", True), ("con_id", 0), ("symbol", " nvda"), ("sec_type", "OPT"),
    ("currency", "EUR"), ("order_type", "LMT"), ("side", "INVALID"), ("account", "FOREIGN")])
def test_malformed_broker_data_fails_closed(tmp_path, field, value):
    repo, _, _, _, _ = submitted(tmp_path)
    original = raw()
    transport = FakeSessionTransport(replace(original, orders=(replace(original.orders[0], **{field: value}),)))
    session = PaperObservationSession(CONFIG, transport)
    runner, _ = build(repo)
    with pytest.raises((ValueError, TypeError)):
        runner.reconcile_session(session)
    assert session.state is SessionState.DEGRADED
    assert ReconciliationStore(reopen(repo)).blocked()


def test_conflicting_duplicate_callbacks_rejected():
    value = raw()
    with pytest.raises(ValueError, match="conflicting"):
        map_snapshot(replace(value, orders=value.orders + (replace(value.orders[0], symbol="AAPL"),)))


def test_query_id_cannot_be_reused_with_changed_facts(tmp_path):
    repo, _, _, _, _ = submitted(tmp_path)
    assess(repo, raw())
    with pytest.raises(VersionConflict, match="query identity"):
        assess(repo, raw(orders=False))
    assert len(ReconciliationStore(repo).reports()) == 1


def test_connected_is_not_ready_and_account_mismatch_degrades():
    transport = FakeSessionTransport(raw())
    session = PaperObservationSession(CONFIG, transport)
    assert session.state is SessionState.DISCONNECTED
    session.connect()
    assert session.state is SessionState.CONNECTED
    transport.accounts = ("FOREIGN",)
    assert session.state is SessionState.DEGRADED


@pytest.mark.parametrize("config", [replace(CONFIG, mode="LIVE"), replace(CONFIG, port=7496),
                                   replace(CONFIG, paper_account_allowlist=())])
def test_paper_config_fails_before_connect(config):
    transport = FakeSessionTransport(raw())
    session = PaperObservationSession(config, transport)
    with pytest.raises(PaperSafetyError):
        session.connect()
    assert not transport.connected and not transport.queries


def test_disconnect_during_query_never_readies(tmp_path):
    repo, _, _, _, _ = submitted(tmp_path)
    transport = FakeSessionTransport(raw())
    transport.on_query = lambda: setattr(transport, "connected", False)
    session = PaperObservationSession(CONFIG, transport)
    runner, _ = build(repo)
    with pytest.raises(PaperSafetyError):
        runner.reconcile_session(session)
    assert session.state is SessionState.DEGRADED
    assert ReconciliationStore(repo).blocked()


def test_execution_evidence_requires_fee_complete_fill_and_does_not_account(tmp_path):
    repo, pending, _, _, _ = submitted(tmp_path)
    event = execution(observed_at=at(10))
    snapshot = raw(orders=False, executions=(event, event))
    report = assess(repo, snapshot)
    assert report.results[0].status is M.UNKNOWN
    assert report.results[1].status is M.LOCAL_ONLY
    assert repo.get(pending.client_order_id).fills == ()
    assert repo.load_portfolio().cash == Decimal("20000")
    assert CODEC.loads(CODEC.dumps(report)) == report


def test_existing_execution_replay_has_no_second_accounting_effect(tmp_path):
    repo, pending, _, adapter, inbox = submitted(tmp_path)
    inbox.append(commission()); inbox.append(execution())
    runner = PaperRunner(repo, adapter)
    runner.consume_inbox(inbox, applied_at=at(9))
    before = runner.account_pending()
    snapshot = raw(orders=False, executions=(execution(observed_at=at(10)),))
    report = assess(repo, snapshot)
    assert report.results[0].status is M.MATCHED
    assess(reopen(repo), snapshot)
    after = repo.load_portfolio()
    assert after.cash == before.cash and dict(after.quantities) == dict(before.quantities)
    assert len(repo.get(pending.client_order_id).fills) == 1


def test_real_transport_still_locked_without_network():
    transport = ReadOnlyIBKRTransport(CONFIG)
    for operation in (lambda: transport.place(None, None), lambda: transport.cancel(None)):
        with pytest.raises(PaperSafetyError, match="locked"):
            operation()


def test_real_readonly_query_seam_uses_raw_callbacks_and_retains_queue():
    transport = ReadOnlyIBKRTransport(CONFIG)
    sample = raw(generation=transport.generation)
    calls = []
    class ClientStub:
        host, port, clientId = CONFIG.host, CONFIG.port, CONFIG.client_id
    class IBStub:
        client = ClientStub()
        def isConnected(self): return True
        def managedAccounts(self): return [CONFIG.account]
        def reqAllOpenOrders(self):
            calls.append("open")
            for event in (*sample.orders, *sample.statuses):
                transport._events.put(event)
        def reqExecutions(self, execution_filter):
            assert execution_filter.acctCode == CONFIG.account
            calls.append("executions")
    transport._ib = IBStub()
    transport._valid = True
    transport._events.put(replace(sample.orders[0], order_id=99))
    result = transport.query_snapshot()
    assert calls == ["open", "executions"]
    assert result.complete and len(map_snapshot(result).orders) == 1
    assert len(transport.read_events()) == 3
    with pytest.raises(PaperSafetyError, match="fresh"):
        transport.query_snapshot()


def test_reconciliation_rejects_concurrent_local_change(tmp_path):
    from tests.ibkr_fakes import saved_pending
    repo, _, _, _, _ = submitted(tmp_path)
    def changing_mapper(payloads):
        saved_pending(repo, cid="concurrent-local-order")
        return owned_identities(payloads)
    store = ReconciliationStore(repo)
    with pytest.raises(VersionConflict, match="changed"):
        store.reconcile(map_snapshot(raw()), changing_mapper)
    assert not store.reports()


def test_orphan_status_does_not_prove_complete_empty_broker():
    snapshot = map_snapshot(raw(orders=False, statuses=(status(),)))
    assert not snapshot.complete and snapshot.diagnostic == "UNPAIRED_STATUS"


def test_session_query_timeout_persists_failure_without_retry(tmp_path):
    repo, _, fake, _, _ = submitted(tmp_path)
    transport = FakeSessionTransport(raw())
    def timeout(): raise TimeoutError("query timed out")
    transport.on_query = timeout
    runner, _ = build(repo)
    session = PaperObservationSession(CONFIG, transport)
    with pytest.raises(TimeoutError):
        runner.reconcile_session(session)
    assert transport.queries == 1 and len(fake.placed) == 1
    assert ReconciliationStore(reopen(repo)).blocked()


def test_later_matched_query_does_not_clear_prior_uncertainty(tmp_path):
    repo, _, _, _, _ = submitted(tmp_path)
    assess(repo, raw(orders=False))
    later = assess(repo, raw(query="later"))
    assert later.matched and ReconciliationStore(repo).blocked()


def test_correction_query_never_books_a_new_execution(tmp_path):
    repo, pending, _, adapter, inbox = submitted(tmp_path)
    inbox.append(commission()); inbox.append(execution())
    runner = PaperRunner(repo, adapter)
    runner.consume_inbox(inbox, applied_at=at(9))
    before = runner.account_pending()
    report = assess(repo, raw(orders=False, executions=(execution("tradeA.02", observed_at=at(10)),)))
    assert report.results[0].status is M.UNKNOWN
    assert len(repo.get(pending.client_order_id).fills) == 1
    assert repo.load_portfolio().cash == before.cash


def test_unknown_and_claim_are_not_cleared_by_matched_query(tmp_path):
    repo, pending, fake, adapter, _ = setup(tmp_path)
    fake.place_error = TimeoutError("possibly delivered")
    runner = PaperRunner(repo, adapter)
    runner.dispatch(pending.client_order_id, applied_at=at(3))
    adapter.registry.resolve(fake.generation, 3, 41, 9001, CONFIG.account)
    before = repo.get(pending.client_order_id)
    session = PaperObservationSession(CONFIG, FakeSessionTransport(raw()))
    report = runner.reconcile_session(session)
    assert report.matched and session.state is SessionState.DEGRADED
    assert repo.get(pending.client_order_id) == before
    assert repo.unresolved_observations()
    assert repo.list_recovery_candidates()[0].claimed_operations == ("submit",)


def test_closed_ready_session_blocks_runner_dispatch(tmp_path):
    repo, pending, _, _, _ = submitted(tmp_path)
    runner, _ = build(repo)
    session = PaperObservationSession(CONFIG, FakeSessionTransport(raw()))
    runner.reconcile_session(session)
    session.close()
    with pytest.raises(ValueError, match="not ready"):
        runner.dispatch(pending.client_order_id, applied_at=at(20))


@pytest.mark.parametrize("field,value", [("shares", 0.5), ("price", Decimal("NaN")),
    ("price", 100.0), ("exec_id", ""), ("side", "BUY"), ("currency", "EUR"),
    ("execution_time", at(20)), ("generation", "stale")])
def test_malformed_execution_is_not_a_fill(field, value):
    with pytest.raises((TypeError, ValueError)):
        map_snapshot(raw(orders=False, executions=(replace(execution(), **{field: value}),)))


def test_inconsistent_active_order_quantity_rejected():
    with pytest.raises(ValueError, match="quantities"):
        map_snapshot(raw(statuses=(status(remaining=0),)))


def test_semantic_dedup_is_independent_of_callback_order(tmp_path):
    from infrastructure.reconciliation import semantic_key
    repo, _, _, _, _ = submitted(tmp_path)
    original = raw()
    other_order = replace(original.orders[0], order_id=42, perm_id=9002)
    other_status = replace(original.statuses[0], order_id=42, perm_id=9002)
    report = assess(repo, replace(original, orders=original.orders + (other_order,),
                                  statuses=original.statuses + (other_status,)))
    reverse = replace(report, snapshot=replace(report.snapshot, orders=tuple(reversed(report.snapshot.orders))),
                      results=tuple(reversed(report.results)))
    assert semantic_key(report) == semantic_key(reverse)
