"""Paper fail-closed and raw callback provenance tests. / Paper 关闭式安全与原始事件来源测试。"""

from dataclasses import replace
from queue import SimpleQueue

import pytest
from ib_insync import CommissionReport, Contract, Execution, IB, Order, OrderStatus, Trade

from broker.ibkr import PaperExecutionConfig, PaperSafetyError, ReadOnlyIBKRTransport
from broker.ibkr.models import CommissionEvent, ErrorEvent, ExecutionEvent, StatusEvent
from broker.ibkr.transport import RawCallbackWrapper
from execution import DispatchOutcome
from tests.ibkr_fakes import CONFIG, at, setup_adapter


@pytest.mark.parametrize("changes", [
    {"mode": "DISABLED"}, {"mode": "LIVE"}, {"mode": "paper"}, {"allow_side_effects": False},
    {"port": 7496}, {"client_id": 0}, {"client_id": True}, {"host": "remote"},
    {"account": ""}, {"paper_account_allowlist": ()}, {"paper_account_allowlist": ("OTHER",)},
])
def test_guard_rejects_unverified_configuration(changes):
    _, pending, fake, adapter, _ = setup_adapter()
    adapter.config = replace(CONFIG, **changes)
    assert adapter.submit(pending).outcome is DispatchOutcome.NOT_SENT
    assert not fake.placed


@pytest.mark.parametrize("changes", [{"generation": "other"}, {"managed_accounts": ("U_LIVE",)},
    {"managed_accounts": ("DU_TEST", "U_LIVE")}, {"client_id": 0}, {"port": 7496}])
def test_guard_checks_actual_session_evidence(changes):
    _, pending, fake, adapter, _ = setup_adapter()
    fake.session = replace(fake.session, **changes)
    assert adapter.submit(pending).outcome is DispatchOutcome.NOT_SENT
    assert not fake.placed


def test_environment_defaults_disabled_and_real_transport_always_locked():
    config = PaperExecutionConfig.from_env({})
    assert config.mode == "DISABLED" and not config.allow_side_effects
    transport = ReadOnlyIBKRTransport(CONFIG)
    try:
        with pytest.raises(PaperSafetyError, match="opt-in"):
            transport.connect_readonly()
        with pytest.raises(PaperSafetyError, match="locked"):
            transport.place(Contract(), Order())
        with pytest.raises(PaperSafetyError, match="locked"):
            transport.cancel(Order())
    finally:
        transport.close()


def test_raw_error_is_not_synthetic_cancel_confirmation():
    ib = IB()
    queue = SimpleQueue()
    wrapper = RawCallbackWrapper(ib, "raw-test", queue)
    wrapper.clientId = 3
    order = Order(orderId=41, clientId=3)
    trade = Trade(Contract(), order, OrderStatus(status="Submitted"))
    wrapper.trades[3, 41] = trade
    high_level = []
    ib.orderStatusEvent += lambda trade: high_level.append(trade.orderStatus.status)
    wrapper.error(41, 201, "rejected", "raw rejection json")
    assert high_level == ["Cancelled"]  # ib_insync synthetic state, not broker orderStatus
    event = queue.get_nowait()
    assert isinstance(event, ErrorEvent) and event.advanced_rejection == "raw rejection json"
    assert queue.empty()


def test_raw_status_duplicates_and_execution_snapshots_survive_library_mutation():
    ib = IB()
    queue = SimpleQueue()
    wrapper = RawCallbackWrapper(ib, "raw-test", queue)
    for _ in range(2):
        wrapper.orderStatus(41, "Submitted", 0, 100, 0, 9001, 0, 0, 3, "")
    assert isinstance(queue.get_nowait(), StatusEvent)
    assert isinstance(queue.get_nowait(), StatusEvent)
    contract = Contract(conId=123, symbol="NVDA", secType="STK", currency="USD")
    execution = Execution(execId="trade.01", acctNumber="DU_TEST", clientId=3, orderId=41,
                          permId=9001, shares=100, price=100, side="BOT", time=at(4))
    wrapper.execDetails(-1, contract, execution)
    snapshot = queue.get_nowait()
    assert isinstance(snapshot, ExecutionEvent) and snapshot.price == 100
    execution.price = 999
    assert snapshot.price == 100
    report = CommissionReport(execId="trade.01", commission=1, currency="USD")
    wrapper.commissionReport(report)
    assert isinstance(queue.get_nowait(), CommissionEvent)


def test_observation_session_closes_on_connect_failure(monkeypatch):
    from broker.ibkr import connection
    closed = []
    class FakeSession:
        def __init__(self, config):
            pass
        def connect_readonly(self, **kwargs):
            raise ConnectionError("fake failure")
        def close(self):
            closed.append(True)
    monkeypatch.setattr(connection, "ReadOnlyIBKRTransport", FakeSession)
    with pytest.raises(ConnectionError):
        with connection.paper_observation_session(CONFIG, integration_opt_in=True):
            pytest.fail("must not enter failed session")
    assert closed == [True]


def test_readonly_session_checks_account_and_invalidates_without_network(monkeypatch):
    transport = ReadOnlyIBKRTransport(CONFIG)
    attempts = []
    def fake_connect(host, port, **kwargs):
        attempts.append(kwargs)
        transport._ib.client.host = host
        transport._ib.client.port = port
        transport._ib.client.clientId = kwargs["clientId"]
    monkeypatch.setattr(transport._ib, "connect", fake_connect)
    monkeypatch.setattr(transport._ib, "isConnected", lambda: True)
    monkeypatch.setattr(transport._ib, "managedAccounts", lambda: ["DU_TEST"])
    monkeypatch.setattr(transport._ib, "disconnect", transport._on_disconnected)
    transport.connect_readonly(integration_opt_in=True)
    assert attempts[0]["readonly"] is True and attempts[0]["clientId"] == 3
    assert transport.evidence().connected
    transport.close()
    assert not transport.evidence().connected
    with pytest.raises(PaperSafetyError, match="fresh"):
        transport.connect_readonly(integration_opt_in=True)
