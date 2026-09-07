"""External-only fake and real domain setup. / 只 fake 外部边界，使用真实 domain。"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from broker.ibkr import IBKRPaperAdapter, IBKREventNormalizer, IdentityRegistry, EquityContractSpec, PaperExecutionConfig
from broker.ibkr.models import CommissionEvent, ExecutionEvent, StatusEvent
from broker.ibkr.transport import SessionEvidence
from execution import (
    ClientOrderId, InMemoryAttemptClaims, InMemoryExecutionOrderRepository,
    SubmissionAuthorization, authorize_execution_order, begin_submission, create_execution_order,
)
from risk import RiskDecision, RiskDecisionStatus
from trading import AssetClass, InstrumentId, OrderRequest, OrderSide


T0 = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
NVDA = InstrumentId(AssetClass.EQUITY, "NVDA")
CONFIG = PaperExecutionConfig("PAPER", account="DU_TEST", paper_account_allowlist=("DU_TEST",),
                              allow_side_effects=True)


def at(seconds):
    return T0 + timedelta(seconds=seconds)


def saved_pending(repo=None, *, cid="local-logical-order", side=OrderSide.BUY, quantity=100):
    repo = InMemoryExecutionOrderRepository() if repo is None else repo
    request = OrderRequest(NVDA, side, quantity, T0)
    order = create_execution_order(request, T0, ClientOrderId(cid))
    repo.add(order)
    authorization = SubmissionAuthorization(order.client_order_id, request, at(1), "operator:test")
    authorized = authorize_execution_order(order, RiskDecision(RiskDecisionStatus.APPROVED, request, T0), authorization)
    repo.save(authorized, order.version)
    pending = begin_submission(authorized, at(2))
    repo.save(pending, authorized.version)
    return repo, pending


class FakeTransport:
    """Records only in-memory calls; no IB object or network. / 仅记录内存调用，不创建 IB 或网络。"""

    generation = "offline-session"

    def __init__(self):
        self.session = SessionEvidence(self.generation, True, "127.0.0.1", 7497, 3, ("DU_TEST",))
        self.placed = []
        self.cancelled = []
        self.counter = 40
        self.place_error = None
        self.cancel_error = None
        self.on_place = None
        self.on_qualify = None

    def evidence(self):
        return self.session

    def preflight(self):
        pass

    def qualify(self, contract):
        contract.conId = 123
        if self.on_qualify:
            self.on_qualify()
        return (contract,)

    def next_order_id(self):
        self.counter += 1
        return self.counter

    def place(self, contract, order):
        self.placed.append((contract, order))
        if self.on_place:
            self.on_place()
        if self.place_error:
            raise self.place_error

    def cancel(self, order):
        self.cancelled.append(order)
        if self.cancel_error:
            raise self.cancel_error


def setup_adapter():
    repo, pending = saved_pending()
    transport = FakeTransport()
    claims = InMemoryAttemptClaims(repo)
    registry = IdentityRegistry()
    adapter = IBKRPaperAdapter(CONFIG, EquityContractSpec(NVDA), transport, claims, registry)
    normalizer = IBKREventNormalizer(registry, transport.generation, CONFIG.client_id)
    return repo, pending, transport, adapter, normalizer


def status(name="Submitted", filled=0, remaining=100, **changes):
    return replace(StatusEvent("offline-session", 3, 41, 9001, name, filled, remaining, at(5)), **changes)


def execution(exec_id="tradeA.01", shares=100, **changes):
    return replace(ExecutionEvent("offline-session", "DU_TEST", 3, 41, 9001, exec_id,
                                   123, "NVDA", "STK", "USD", "BOT", shares, Decimal("100"), at(4), at(6)), **changes)


def commission(exec_id="tradeA.01", value="1", **changes):
    return replace(CommissionEvent("offline-session", exec_id, Decimal(value), "USD", at(8)), **changes)
