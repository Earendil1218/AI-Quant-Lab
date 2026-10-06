"""Production Paper boundary with external client methods replaced; no network."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from threading import Barrier

import pytest
from ib_insync import CommissionReport, Execution, Order, OrderState

from application import PaperRunner
from broker.ibkr import IBKRPaperAdapter, EquityContractSpec
from broker.ibkr.config import PaperSafetyError
from broker.ibkr.paper_transport import PaperExecutionTransport, PaperSessionConfirmation
from broker.ibkr.recovery import PersistentIdentityRegistry
from execution import ClientOrderId, DispatchOperation, DispatchOutcome, SubmissionAuthorization
from execution.models import ExecutionOrderState as State
from infrastructure import SQLiteAttemptClaims, SQLiteExecutionRepository
from infrastructure.reconciliation import ReconciliationStore
from portfolio.sizing import FixedQuantitySizing
from risk import RiskConfiguration, ValuationContext
from tests.ibkr_fakes import CONFIG, NVDA, at
from trading import TargetExposureIntent


class ExternalClient:
    """Only IB socket-facing methods are fake; raw wrapper/adapter/store stay real."""

    def __init__(self, transport, monkeypatch):
        self.transport = transport
        self.connected = False
        self.calls = []
        self.ids = 40
        self.qualify_hook = None
        self.id_hook = None
        self.place_hook = None
        self.open_hook = None
        self.exec_hook = None
        self.accounts = (CONFIG.account,)
        ib = transport._ib
        for name in ('connect', 'disconnect', 'isConnected', 'managedAccounts',
                     'qualifyContracts', 'placeOrder', 'reqAllOpenOrders', 'reqExecutions'):
            monkeypatch.setattr(ib, name, getattr(self, name))
        monkeypatch.setattr(ib.client, 'getReqId', self.getReqId)

    def connect(self, host, port, *, clientId, readonly, account, timeout):
        assert readonly is False and account == CONFIG.account
        self.connected = True
        self.transport._ib.client.host = host
        self.transport._ib.client.port = port
        self.transport._ib.client.clientId = clientId

    def disconnect(self):
        if self.connected:
            self.connected = False
            self.transport._on_disconnected()

    def isConnected(self):
        return self.connected

    def managedAccounts(self):
        return self.accounts

    def qualifyContracts(self, contract):
        if self.qualify_hook:
            self.qualify_hook(contract)
        contract.conId = 123
        return [contract]

    def getReqId(self):
        if self.id_hook:
            self.id_hook()
        self.ids += 1
        return self.ids

    def placeOrder(self, contract, order):
        self.calls.append((contract, order))
        if self.place_hook:
            self.place_hook(contract, order)

    def reqAllOpenOrders(self):
        if self.open_hook:
            self.open_hook()
        return []

    def reqExecutions(self, filter):
        if self.exec_hook:
            self.exec_hook()
        return []


def confirmation(transport, **changes):
    return replace(PaperSessionConfirmation(transport.generation, CONFIG.account, 'operator:test',
                   'I verified this exact account is Simulated/Paper in TWS'), **changes)


def build(tmp_path, monkeypatch, *, start=True, config=CONFIG):
    repo = SQLiteExecutionRepository(tmp_path / 'paper.db')
    repo.initialize_accounting(Decimal('20000'))
    transport = PaperExecutionTransport(config)
    external = ExternalClient(transport, monkeypatch)
    adapter = IBKRPaperAdapter(config, EquityContractSpec(NVDA), transport,
                              SQLiteAttemptClaims(repo), PersistentIdentityRegistry(repo, transport.generation))
    runner = PaperRunner(repo, adapter)
    if start:
        assert runner.start_paper_session(confirmation(transport), integration_opt_in=True,
                                         side_effect_opt_in=True).matched
    return repo, transport, external, adapter, runner


def prepare(runner):
    ticket = runner.plan(TargetExposureIntent(NVDA, at(0), 1.0, 'manual', 'long'),
                         FixedQuantitySizing(100), RiskConfiguration(maximum_order_quantity=100),
                         ValuationContext(at(0), {NVDA: Decimal('100')}))
    auth = SubmissionAuthorization(ClientOrderId('paper-loop'), ticket.plan.request, at(1), 'operator:test')
    return runner.prepare(ticket, auth, prepared_at=at(2))


def assert_unclaimed(adapter, pending):
    adapter.claims.validate(pending, DispatchOperation.SUBMIT)


@pytest.mark.parametrize('integration,side', [(False, False), (True, False), (False, True), (1, True)])
def test_double_opt_in_required_before_connect(tmp_path, monkeypatch, integration, side):
    _, transport, external, _, _ = build(tmp_path, monkeypatch, start=False)
    with pytest.raises(PaperSafetyError):
        transport.connect_paper(confirmation(transport), integration_opt_in=integration, side_effect_opt_in=side)
    assert not external.connected and not external.calls


def test_default_and_direct_transport_cannot_send(tmp_path, monkeypatch):
    _, transport, external, _, runner = build(tmp_path, monkeypatch, start=False)
    with pytest.raises(PaperSafetyError):
        transport.place(None, Order())
    with pytest.raises(ValueError, match='startup'):
        runner.plan(None, None, None, None)
    assert not external.calls


@pytest.mark.parametrize('changes', [dict(account='OTHER'), dict(generation='old'),
                                     dict(confirmed_by=''), dict(declaration='PAPER')])
def test_confirmation_exact_current_account(tmp_path, monkeypatch, changes):
    _, transport, external, _, _ = build(tmp_path, monkeypatch, start=False)
    with pytest.raises(PaperSafetyError):
        transport.connect_paper(confirmation(transport, **changes), integration_opt_in=True, side_effect_opt_in=True)
    assert not external.connected


@pytest.mark.parametrize('field,value', [('host', 'remote'), ('port', 7496), ('clientId', 9)])
def test_endpoint_mismatch_does_not_claim(tmp_path, monkeypatch, field, value):
    _, transport, external, adapter, runner = build(tmp_path, monkeypatch)
    pending = prepare(runner)
    setattr(transport._ib.client, field, value)
    result = adapter.submit(pending)
    assert result.outcome is DispatchOutcome.NOT_SENT
    assert_unclaimed(adapter, pending)
    assert external.ids == 40 and not external.calls


@pytest.mark.parametrize('kind', ['account', 'generation', 'disconnect', 'config'])
def test_session_and_config_mutation_fail_closed(tmp_path, monkeypatch, kind):
    _, transport, external, adapter, runner = build(tmp_path, monkeypatch)
    pending = prepare(runner)
    if kind == 'account':
        external.accounts = ('OTHER',)
    elif kind == 'generation':
        transport.generation = 'stale'
    elif kind == 'disconnect':
        external.disconnect()
    else:
        transport.config = replace(CONFIG, account='OTHER', paper_account_allowlist=('OTHER',))
    assert adapter.submit(pending).outcome is DispatchOutcome.NOT_SENT
    assert_unclaimed(adapter, pending)
    assert external.ids == 40 and not external.calls


@pytest.mark.parametrize('failure', ['qualification', 'mapping', 'late_preflight'])
def test_preparation_failures_preserve_claim(tmp_path, monkeypatch, failure):
    _, transport, external, adapter, runner = build(tmp_path, monkeypatch)
    pending = prepare(runner)
    if failure == 'qualification':
        def fail(contract):
            raise ValueError('qualification failed')
        external.qualify_hook = fail
    elif failure == 'mapping':
        adapter.spec = EquityContractSpec(replace(NVDA, symbol='AAPL'))
    else:
        external.qualify_hook = lambda contract: setattr(external, 'accounts', ('OTHER',))
    if failure == 'late_preflight':
        assert adapter.submit(pending).outcome is DispatchOutcome.NOT_SENT
    else:
        with pytest.raises(ValueError):
            adapter.submit(pending)
    assert_unclaimed(adapter, pending)
    assert external.ids == 40 and not external.calls


def test_success_sends_once_and_restart_retains_claim(tmp_path, monkeypatch):
    repo, transport, external, adapter, runner = build(tmp_path, monkeypatch)
    pending = prepare(runner)
    assert runner.dispatch(pending.client_order_id, applied_at=at(3)).outcome is DispatchOutcome.DISPATCH_RETURNED
    assert len(external.calls) == 1 and external.ids == 41
    with pytest.raises(ValueError):
        adapter.submit(pending)
    fresh = SQLiteExecutionRepository(repo.path)
    with pytest.raises(ValueError, match='already claimed'):
        SQLiteAttemptClaims(fresh).validate(pending, DispatchOperation.SUBMIT)
    assert len(PersistentIdentityRegistry(fresh, transport.generation).bindings()) == 1


def test_concurrent_duplicate_dispatch_is_one_attempt(tmp_path, monkeypatch):
    _, _, external, adapter, runner = build(tmp_path, monkeypatch)
    pending = prepare(runner)
    barrier = Barrier(2)
    def dispatch():
        barrier.wait(timeout=5)
        try:
            return adapter.submit(pending).outcome
        except ValueError:
            return 'duplicate'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: dispatch(), range(2)))
    assert results.count(DispatchOutcome.DISPATCH_RETURNED) == 1
    assert len(external.calls) == 1 and external.ids == 41


def test_before_api_failure_is_not_sent_but_claim_stays_consumed(tmp_path, monkeypatch):
    _, _, external, adapter, runner = build(tmp_path, monkeypatch)
    pending = prepare(runner)
    def fail():
        raise RuntimeError('ID allocation failed')
    external.id_hook = fail
    result = runner.dispatch(pending.client_order_id, applied_at=at(3))
    assert result.outcome is DispatchOutcome.NOT_SENT and not external.calls
    with pytest.raises(ValueError, match='claimed'):
        adapter.claims.validate(pending, DispatchOperation.SUBMIT)


@pytest.mark.parametrize('failure', ['timeout', 'disconnect', 'reserved_not_sent'])
def test_after_api_entry_is_unknown_never_retried(tmp_path, monkeypatch, failure):
    repo, _, external, adapter, runner = build(tmp_path, monkeypatch)
    pending = prepare(runner)
    def fail(contract, order):
        if failure == 'disconnect':
            external.disconnect()
        elif failure == 'reserved_not_sent':
            from broker.ibkr.paper_transport import PaperNotSentError
            raise PaperNotSentError('API already entered despite exception name')
        else:
            raise TimeoutError('unknown delivery')
    external.place_hook = fail
    assert runner.dispatch(pending.client_order_id, applied_at=at(3)).outcome is DispatchOutcome.DELIVERY_UNKNOWN
    assert repo.get(pending.client_order_id).state is State.UNKNOWN
    with pytest.raises(ValueError):
        runner.dispatch(pending.client_order_id, applied_at=at(4))
    assert len(external.calls) == 1


def test_disconnect_and_reconciliation_block_new_planning(tmp_path, monkeypatch):
    repo, _, external, _, runner = build(tmp_path, monkeypatch)
    ReconciliationStore(repo).failure('other-generation', 'MANUAL_REVIEW_REQUIRED')
    with pytest.raises(ValueError, match='reconciliation'):
        prepare(runner)
    external.disconnect()
    with pytest.raises(PaperSafetyError):
        prepare(runner)


def test_real_cancel_remains_locked_and_session_cannot_reconnect(tmp_path, monkeypatch):
    _, transport, external, _, _ = build(tmp_path, monkeypatch)
    with pytest.raises(PaperSafetyError, match='cancellation'):
        transport.cancel(Order())
    transport.close()
    with pytest.raises(PaperSafetyError, match='reconnect'):
        transport.connect_paper(confirmation(transport), integration_opt_in=True, side_effect_opt_in=True)
    assert not external.calls


def test_raw_callbacks_fill_account_duplicate_and_fresh_match(tmp_path, monkeypatch):
    repo, transport, external, _, runner = build(tmp_path, monkeypatch)
    pending = prepare(runner)
    runner.dispatch(pending.client_order_id, applied_at=at(3))
    contract, order = external.calls[0]
    order.permId = 9001
    wrapper = transport._ib.wrapper
    wrapper.openOrder(41, contract, order, OrderState(status='Submitted'))
    wrapper.orderStatus(41, 'Submitted', 0, 100, 0, 9001, 0, 0, 3, '')
    runner.ingest_callbacks(applied_at=datetime.now(timezone.utc))
    assert repo.get(pending.client_order_id).state is State.ACKNOWLEDGED
    execution = Execution(execId='loop.01', acctNumber=CONFIG.account, clientId=3, orderId=41,
                          permId=9001, side='BOT', shares=100, price=100, time=at(4))
    wrapper.execDetails(-1, contract, execution)
    wrapper.commissionReport(CommissionReport(execId='loop.01', commission=1, currency='USD'))
    wrapper.orderStatus(41, 'Filled', 100, 0, 100, 9001, 0, 100, 3, '')
    runner.ingest_callbacks(applied_at=datetime.now(timezone.utc))
    assert repo.get(pending.client_order_id).state is State.FILLED
    assert runner.account_pending().cash == Decimal('9999')
    wrapper.execDetails(-1, contract, execution)
    wrapper.commissionReport(CommissionReport(execId='loop.01', commission=1, currency='USD'))
    runner.ingest_callbacks(applied_at=datetime.now(timezone.utc))
    assert runner.account_pending().cash == Decimal('9999')
    external.exec_hook = lambda: wrapper.execDetails(-1, contract, execution)
    report = runner.reconcile_paper()
    assert report.matched and len(report.snapshot.executions) == 1
    runner.ingest_callbacks(applied_at=datetime.now(timezone.utc))
    assert runner.account_pending().cash == Decimal('9999')
    assert repo.pending_inbox_count() == repo.pending_accounting_count() == 0
    assert len(repo.get(pending.client_order_id).fills) == 1 and len(external.calls) == 1

def test_pending_callbacks_block_planning_and_dispatch_without_claim(tmp_path, monkeypatch):
    _, transport, external, adapter, runner = build(tmp_path, monkeypatch)
    pending = prepare(runner)
    from broker.ibkr.models import CommissionEvent
    transport._events.put(CommissionEvent(transport.generation, 'foreign.01', Decimal('1'), 'USD', at(4)))
    with pytest.raises(ValueError, match='raw callbacks'):
        runner.plan(None, None, None, None)
    assert adapter.submit(pending).outcome is DispatchOutcome.NOT_SENT
    assert_unclaimed(adapter, pending)
    assert not external.calls


def test_foreign_raw_order_is_retained_not_adopted(tmp_path, monkeypatch):
    repo, transport, _, _, runner = build(tmp_path, monkeypatch)
    from ib_insync import Stock
    order = Order(orderId=999, clientId=3, account=CONFIG.account, permId=111,
                  action='BUY', totalQuantity=1, orderType='MKT', orderRef='manual')
    transport._ib.wrapper.openOrder(999, Stock('NVDA', 'SMART', 'USD', conId=123),
                                   order, OrderState(status='Submitted'))
    with pytest.raises(KeyError):
        runner.ingest_callbacks(applied_at=datetime.now(timezone.utc))
    assert repo.pending_inbox_count() == 1
    assert ReconciliationStore(repo).blocked()
    assert not PersistentIdentityRegistry(repo, transport.generation).bindings()


def test_memory_claims_cannot_unlock_production_transport(tmp_path, monkeypatch):
    repo, _, external, adapter, runner = build(tmp_path, monkeypatch)
    pending = prepare(runner)
    from execution import InMemoryAttemptClaims
    adapter.claims = InMemoryAttemptClaims(repo)
    assert adapter.submit(pending).outcome is DispatchOutcome.NOT_SENT
    assert not external.calls and external.ids == 40


@pytest.mark.parametrize('field,value', [('mode', 'LIVE'), ('allow_side_effects', False),
                                       ('port', 7496), ('paper_account_allowlist', ('OTHER',))])
def test_invalid_paper_config_never_connects(tmp_path, monkeypatch, field, value):
    _, transport, external, _, _ = build(tmp_path, monkeypatch, start=False, config=replace(CONFIG, **{field: value}))
    with pytest.raises(PaperSafetyError):
        transport.connect_paper(confirmation(transport), integration_opt_in=True, side_effect_opt_in=True)
    assert not external.connected and not external.calls


def test_late_pre_api_failure_after_claim_is_provably_not_sent(tmp_path, monkeypatch):
    _, _, external, adapter, runner = build(tmp_path, monkeypatch)
    pending = prepare(runner)
    original = adapter.registry.register
    def register(binding):
        original(binding)
        external.accounts = ('OTHER',)
    monkeypatch.setattr(adapter.registry, 'register', register)
    assert runner.dispatch(pending.client_order_id, applied_at=at(3)).outcome is DispatchOutcome.NOT_SENT
    assert not external.calls and external.ids == 41
    with pytest.raises(ValueError, match='claimed'):
        adapter.claims.validate(pending, DispatchOperation.SUBMIT)


@pytest.mark.parametrize('integration,side,environment', [(False, False, True), (True, False, True),
                                                        (True, True, False)])
def test_manual_harness_gates_cannot_be_inferred(tmp_path, monkeypatch, integration, side, environment):
    from application.paper_integration import run_authorized_paper_loop
    _, transport, external, _, runner = build(tmp_path, monkeypatch, start=False)
    if environment:
        monkeypatch.setenv('RUN_IBKR_PAPER_INTEGRATION', '1')
        monkeypatch.setenv('ALLOW_IBKR_PAPER_ORDER_SIDE_EFFECTS', 'YES')
    else:
        monkeypatch.delenv('RUN_IBKR_PAPER_INTEGRATION', raising=False)
        monkeypatch.delenv('ALLOW_IBKR_PAPER_ORDER_SIDE_EFFECTS', raising=False)
    with pytest.raises(PaperSafetyError):
        run_authorized_paper_loop(runner, confirmation=confirmation(transport), intent=None,
            sizing=None, risk_configuration=None, valuation=None, authorization=None,
            integration_opt_in=integration, side_effect_opt_in=side)
    assert not external.connected and not external.calls


def test_manual_harness_offline_full_loop_uses_supplied_authority(tmp_path, monkeypatch):
    from application.paper_integration import run_authorized_paper_loop
    from trading import OrderRequest, OrderSide
    repo, transport, external, _, runner = build(tmp_path, monkeypatch, start=False)
    monkeypatch.setenv('RUN_IBKR_PAPER_INTEGRATION', '1')
    monkeypatch.setenv('ALLOW_IBKR_PAPER_ORDER_SIDE_EFFECTS', 'YES')
    execution = Execution(execId='harness.01', acctNumber=CONFIG.account, clientId=3, orderId=41,
                          permId=9001, side='BOT', shares=100, price=100, time=at(4))
    def callbacks(contract, order):
        order.permId = 9001
        wrapper = transport._ib.wrapper
        wrapper.openOrder(41, contract, order, OrderState(status='PreSubmitted'))
        wrapper.orderStatus(41, 'PreSubmitted', 0, 100, 0, 9001, 0, 0, 3, '')
        wrapper.orderStatus(41, 'Filled', 100, 0, 100, 9001, 0, 100, 3, '')
        wrapper.execDetails(-1, contract, execution)
        wrapper.commissionReport(CommissionReport(execId='harness.01', commission=1, currency='USD'))
        external.exec_hook = lambda: wrapper.execDetails(-1, contract, execution)
    external.place_hook = callbacks
    auth = SubmissionAuthorization(ClientOrderId('manual-harness'),
                                   OrderRequest(NVDA, OrderSide.BUY, 100, at(0)), at(1), 'operator:test')
    result = run_authorized_paper_loop(runner, confirmation=confirmation(transport),
        intent=TargetExposureIntent(NVDA, at(0), 1.0, 'manual', 'long'), sizing=FixedQuantitySizing(100),
        risk_configuration=RiskConfiguration(maximum_order_quantity=100),
        valuation=ValuationContext(at(0), {NVDA: Decimal('100')}), authorization=auth,
        integration_opt_in=True, side_effect_opt_in=True)
    assert result.reconciliation.matched and result.order.state is State.FILLED
    assert result.order.authorization == auth
    assert repo.load_portfolio().cash == Decimal('9999')
    assert not repo.unresolved_observations() and not external.connected
    assert len(external.calls) == 1

def test_post_fill_completion_audit_never_clears_other_uncertainty(tmp_path, monkeypatch):
    from execution import ExecutionObservation, ObservationKind
    from tests.ibkr_fakes import execution, commission
    repo, transport, external, _, runner = build(tmp_path, monkeypatch)
    pending = prepare(runner)
    runner.dispatch(pending.client_order_id, applied_at=at(3))
    transport._events.put(replace(commission(), generation=transport.generation))
    transport._events.put(replace(execution(), generation=transport.generation))
    runner.ingest_callbacks(applied_at=at(9))
    filled = repo.get(pending.client_order_id)
    assert filled.state is State.FILLED
    uncertain = ExecutionObservation(filled.client_order_id, filled.request, ObservationKind.UNRESOLVED,
                                    at(10), filled.broker_order_id, detail='requires independent review')
    runner.consume(uncertain, applied_at=at(10))
    conflict = ExecutionObservation(filled.client_order_id, filled.request, ObservationKind.COMPLETION,
                                   at(11), filled.broker_order_id, reported_filled_quantity=99)
    runner.consume(conflict, applied_at=at(11))
    complete = replace(conflict, observed_at=at(12), reported_filled_quantity=100)
    runner.consume(complete, applied_at=at(12))
    assert repo.unresolved_observations() == (uncertain, conflict)
    assert runner.account_pending().cash == Decimal('9999')
    fresh = SQLiteExecutionRepository(repo.path)
    assert fresh.unresolved_observations() == (uncertain, conflict)
    with fresh._transaction() as db:
        assert db.execute("SELECT count(*) FROM observations WHERE reason='completion' AND resolved_by LIKE 'fee-complete:%'").fetchone()[0] == 1
    assert len(external.calls) == 1


def test_real_sell_is_locked_without_broker_inventory(tmp_path, monkeypatch):
    from trading import OrderRequest, OrderSide
    repo, transport, external, adapter, _ = build(tmp_path, monkeypatch)
    # This boundary must reject SELL even if local planning/accounting were wired
    # incorrectly. A local portfolio alone cannot establish broker long inventory.
    from tests.ibkr_fakes import saved_pending
    _, pending = saved_pending(repo, side=OrderSide.SELL)
    with transport._dispatch_scope(pending, adapter.claims, adapter.registry, CONFIG, adapter.spec):
        monkeypatch.setattr(repo, 'validate_planned', lambda _: None)
        with pytest.raises(PaperSafetyError, match='SELL'):
            transport.preflight()
    assert_unclaimed(adapter, pending)
    assert not external.calls and external.ids == 40

def test_repeated_fresh_matching_query_preserves_readiness(tmp_path, monkeypatch):
    repo, transport, _, _, runner = build(tmp_path, monkeypatch)
    first = ReconciliationStore(repo).reports()[0]
    second = runner.reconcile_paper()
    assert second.matched and second.snapshot.query_id != first.snapshot.query_id
    assert len(ReconciliationStore(repo).reports()) == 1
    assert prepare(runner).state is State.SUBMISSION_PENDING


def test_manual_harness_deadline_is_unknown_without_retry(tmp_path, monkeypatch):
    import application.paper_integration as harness
    from trading import OrderRequest, OrderSide
    repo, transport, external, _, runner = build(tmp_path, monkeypatch, start=False)
    monkeypatch.setenv('RUN_IBKR_PAPER_INTEGRATION', '1')
    monkeypatch.setenv('ALLOW_IBKR_PAPER_ORDER_SIDE_EFFECTS', 'YES')
    times = iter([0.0, 31.0])
    monkeypatch.setattr(harness, 'monotonic', lambda: next(times))
    auth = SubmissionAuthorization(ClientOrderId('deadline'), OrderRequest(NVDA, OrderSide.BUY, 100, at(0)),
                                   at(1), 'operator:test')
    result = harness.run_authorized_paper_loop(runner, confirmation=confirmation(transport),
        intent=TargetExposureIntent(NVDA, at(0), 1.0, 'manual', 'long'), sizing=FixedQuantitySizing(100),
        risk_configuration=RiskConfiguration(maximum_order_quantity=100),
        valuation=ValuationContext(at(0), {NVDA: Decimal('100')}), authorization=auth,
        integration_opt_in=True, side_effect_opt_in=True)
    assert result.order.state is State.UNKNOWN and result.reconciliation is None
    assert repo.unresolved_observations() and len(external.calls) == 1
    assert not external.connected

def test_live_account_identifier_cannot_connect_even_with_false_confirmation(tmp_path, monkeypatch):
    live = replace(CONFIG, account='U1234567', paper_account_allowlist=('U1234567',))
    _, transport, external, _, _ = build(tmp_path, monkeypatch, start=False, config=live)
    with pytest.raises(PaperSafetyError, match='DU Paper'):
        transport.connect_paper(confirmation(transport, account=live.account),
                                integration_opt_in=True, side_effect_opt_in=True)
    assert not external.connected and not external.calls


def test_broker_session_loss_retires_even_connected_socket(tmp_path, monkeypatch):
    repo, transport, external, _, runner = build(tmp_path, monkeypatch)
    transport._ib.wrapper.error(-1, 1100, 'connectivity lost')
    assert external.connected and not transport.evidence().connected
    runner.ingest_callbacks(applied_at=datetime.now(timezone.utc))
    with pytest.raises(PaperSafetyError):
        prepare(runner)
    # A later recovery notice cannot restore this generation's authority.
    transport._ib.wrapper.error(-1, 1102, 'connectivity restored')
    assert not transport.evidence().connected and not external.calls

def test_consumed_claim_cannot_reenter_transport_scope(tmp_path, monkeypatch):
    _, transport, external, adapter, runner = build(tmp_path, monkeypatch)
    pending = prepare(runner)
    def fail_id():
        raise RuntimeError('pre-entry ID failure')
    external.id_hook = fail_id
    assert adapter.submit(pending).outcome is DispatchOutcome.NOT_SENT
    external.id_hook = None
    scope = transport._dispatch_scope
    with pytest.raises(ValueError, match='claimed'):
        with scope(pending, adapter.claims, adapter.registry, CONFIG, adapter.spec):
            order_id = transport.next_order_id()
    assert external.ids == 40 and not external.calls


@pytest.mark.parametrize('loss', ['error', 'disconnect'])
def test_loss_during_connect_cannot_restore_generation(tmp_path, monkeypatch, loss):
    _, transport, external, _, _ = build(tmp_path, monkeypatch, start=False)
    connect = external.connect
    def lose_during_connect(*args, **kwargs):
        connect(*args, **kwargs)
        if loss == 'error':
            transport._ib.wrapper.error(-1, 1100, 'loss during handshake')
        else:
            external.disconnect()
            external.connected = True  # Socket reconnect does not restore authority.
    monkeypatch.setattr(transport._ib, 'connect', lose_during_connect)
    with pytest.raises(PaperSafetyError):
        transport.connect_paper(confirmation(transport), integration_opt_in=True, side_effect_opt_in=True)
    assert not transport.evidence().connected and not external.calls


def test_final_contract_spec_cannot_change_authorized_instrument(tmp_path, monkeypatch):
    from broker.ibkr.mapping import map_order
    _, transport, external, adapter, runner = build(tmp_path, monkeypatch)
    pending = prepare(runner)
    # Stop after the genuine mapping/qualification/claim/ownership preparation.
    with monkeypatch.context() as local_patch:
        local_patch.setattr(transport, 'place', lambda *args: None)
        assert adapter.submit(pending).outcome is DispatchOutcome.DISPATCH_RETURNED
    # The genuine public boundary must reject inconsistent symbol/spec even if
    # a caller manually composes its internals with a consumed claim.
    from ib_insync import Stock
    contract = Stock('AAPL', 'SMART', 'USD', conId=123)
    binding = adapter.registry.get(pending.client_order_id)
    mapped = map_order(pending.request, binding.identity)
    transport._active = (pending, adapter.claims, adapter.registry, CONFIG,
                         EquityContractSpec(replace(NVDA, symbol='AAPL')))
    try:
        with pytest.raises(PaperSafetyError):
            transport.place(contract, mapped)
    finally:
        transport._active = None
    assert not external.calls

def planned_sell(repo, transport, runner):
    from tests.ibkr_fakes import execution, commission
    pending = prepare(runner)
    assert runner.dispatch(pending.client_order_id, applied_at=at(3)).outcome is DispatchOutcome.DISPATCH_RETURNED
    transport._events.put(replace(commission(), generation=transport.generation))
    transport._events.put(replace(execution(), generation=transport.generation))
    runner.ingest_callbacks(applied_at=at(9))
    runner.account_pending()
    assert repo.load_portfolio().quantity_for(NVDA) == 100
    ticket = runner.plan(TargetExposureIntent(NVDA, at(10), 0.0, 'manual', 'flat'),
                         FixedQuantitySizing(100), RiskConfiguration(maximum_order_quantity=100),
                         ValuationContext(at(10), {NVDA: Decimal('100')}))
    from trading import OrderSide
    assert ticket.plan.request.side is OrderSide.SELL
    auth = SubmissionAuthorization(ClientOrderId('locked-sell'), ticket.plan.request, at(11), 'operator:test')
    return runner.prepare(ticket, auth, prepared_at=at(12))


@pytest.mark.parametrize('path', ['adapter', 'runner', 'recovered', 'concurrent'])
def test_genuinely_planned_sell_never_consumes_claim_or_sends(tmp_path, monkeypatch, path):
    repo, transport, external, adapter, runner = build(tmp_path, monkeypatch)
    pending = planned_sell(repo, transport, runner)
    if path == 'recovered':
        fresh = SQLiteExecutionRepository(repo.path)
        pending = fresh.get(pending.client_order_id)
        adapter = IBKRPaperAdapter(CONFIG, EquityContractSpec(NVDA), transport,
                                  SQLiteAttemptClaims(fresh), PersistentIdentityRegistry(fresh, transport.generation))
        assert adapter.submit(pending).outcome is DispatchOutcome.NOT_SENT
    elif path == 'runner':
        assert runner.dispatch(pending.client_order_id, applied_at=at(13)).outcome is DispatchOutcome.NOT_SENT
    elif path == 'concurrent':
        barrier = Barrier(2)
        def dispatch():
            barrier.wait(timeout=5)
            return adapter.submit(pending).outcome
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(lambda _: dispatch(), range(2))) == [DispatchOutcome.NOT_SENT] * 2
    else:
        assert adapter.submit(pending).outcome is DispatchOutcome.NOT_SENT
    assert_unclaimed(adapter, pending)
    # Exactly one initial BUY seeded LOCAL inventory; no SELL call or broker ID.
    assert len(external.calls) == 1 and external.ids == 41
    assert repo.load_portfolio().quantity_for(NVDA) == 100
    assert repo.get(pending.client_order_id).state is State.SUBMISSION_PENDING


def test_mutated_side_snapshot_cannot_bypass_saved_authority(tmp_path, monkeypatch):
    from trading import OrderSide
    _, _, external, adapter, runner = build(tmp_path, monkeypatch)
    pending = prepare(runner)
    object.__setattr__(pending.request, 'side', OrderSide.SELL)
    with pytest.raises(ValueError, match='current saved order'):
        adapter.submit(pending)
    assert not external.calls and external.ids == 40


def test_risk_pass_without_human_authorization_has_no_send_capability(tmp_path, monkeypatch):
    from execution import create_execution_order
    from risk import RiskDecisionStatus
    repo, transport, external, adapter, runner = build(tmp_path, monkeypatch)
    ticket = runner.plan(TargetExposureIntent(NVDA, at(0), 1.0, 'manual', 'long'),
                         FixedQuantitySizing(100), RiskConfiguration(maximum_order_quantity=100),
                         ValuationContext(at(0), {NVDA: Decimal('100')}))
    assert ticket.risk_decision.status is RiskDecisionStatus.APPROVED
    order = create_execution_order(ticket.plan.request, at(0), ClientOrderId('no-human-approval'))
    repo.add(order)
    with pytest.raises(ValueError, match='authorized pending intent'):
        adapter.submit(order)
    assert repo.get(order.client_order_id).authorization is None
    assert not external.calls and external.ids == 40
    assert not hasattr(transport, 'dispatch_scope')
    with pytest.raises(PaperSafetyError):
        transport.place(None, Order())

def test_independent_paper_transports_race_on_one_durable_claim(tmp_path, monkeypatch):
    _, _, first_external, first_adapter, runner = build(tmp_path, monkeypatch)
    _, _, second_external, second_adapter, _ = build(tmp_path, monkeypatch, config=replace(CONFIG, client_id=4))
    pending = prepare(runner)
    prepared = Barrier(2)
    first_external.qualify_hook = lambda contract: prepared.wait(timeout=5)
    second_external.qualify_hook = lambda contract: prepared.wait(timeout=5)
    def dispatch(adapter):
        try:
            return adapter.submit(pending).outcome
        except ValueError:
            return 'duplicate'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(dispatch, (first_adapter, second_adapter)))
    assert results.count(DispatchOutcome.DISPATCH_RETURNED) == 1
    assert len(first_external.calls) + len(second_external.calls) == 1
    assert first_external.ids + second_external.ids == 81

def test_uncorrelated_unknown_broker_error_is_a_durable_blocker(tmp_path, monkeypatch):
    repo, transport, external, _, runner = build(tmp_path, monkeypatch)
    transport._ib.wrapper.error(-1, 999999, 'unclassified diagnostic')
    assert not transport.evidence().connected
    runner.ingest_callbacks(applied_at=datetime.now(timezone.utc))
    assert ReconciliationStore(repo).blocked()
    fresh = SQLiteExecutionRepository(repo.path)
    assert ReconciliationStore(fresh).blocked()
    assert fresh.evidence('reconciliation-failures:v1')
    with pytest.raises(PaperSafetyError):
        prepare(runner)
    assert not external.calls


def test_informational_broker_error_does_not_invent_uncertainty(tmp_path, monkeypatch):
    repo, transport, external, _, runner = build(tmp_path, monkeypatch)
    transport._ib.wrapper.error(-1, 2104, 'market data farm connected')
    runner.ingest_callbacks(applied_at=datetime.now(timezone.utc))
    assert transport.evidence().connected and not ReconciliationStore(repo).blocked()
    assert prepare(runner).state is State.SUBMISSION_PENDING
    assert not external.calls

def test_unknown_diagnostic_replay_after_raw_commit_cannot_clear_blocker(tmp_path, monkeypatch):
    from broker.ibkr.recovery import PersistentIBKRInbox
    from tests.test_paper_runner import build as build_offline_runner
    repo, transport, external, _, _ = build(tmp_path, monkeypatch)
    transport._ib.wrapper.error(-1, 999999, 'unclassified before crash')
    inbox = PersistentIBKRInbox(repo, transport.generation, CONFIG.client_id)
    for event in transport.read_events():
        inbox.append(event)
    # Crash before normalization/failure persistence, then use the existing
    # generic recovery API rather than the live ingestion application method.
    assert repo.pending_inbox_count() == 1 and not ReconciliationStore(repo).blocked()
    fresh = SQLiteExecutionRepository(repo.path)
    runner, _ = build_offline_runner(fresh)
    runner.consume_inbox(PersistentIBKRInbox(fresh, transport.generation, CONFIG.client_id),
                         applied_at=datetime.now(timezone.utc))
    assert fresh.pending_inbox_count() == 0
    assert ReconciliationStore(fresh).blocked()
    assert ReconciliationStore(SQLiteExecutionRepository(repo.path)).blocked()
    with pytest.raises(ValueError, match='reconciliation'):
        runner.plan(None, None, None, None)
    assert not external.calls
