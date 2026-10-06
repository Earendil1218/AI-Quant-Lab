"""Immutable broker-neutral query facts; never execution authority.

查询事实与执行授权分离；不通过状态快照制造成交。
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from execution.models import ClientOrderId, ExecutionOrder
from trading import InstrumentId, OrderSide


class BrokerState(str, Enum):
    PENDING = "pending"
    WORKING = "working"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    FILLED = "filled"
    UNKNOWN = "unknown"


def text(value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("nonempty exact identity required")


def timestamp(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("aware observation timestamp required")


def quantity(value: int, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError("invalid integral quantity")


@dataclass(frozen=True)
class ObservedIdentity:
    account: str
    generation: str
    client: str
    api_order: str
    permanent: str | None

    def __post_init__(self) -> None:
        for value in (self.account, self.generation, self.client, self.api_order):
            text(value)
        if self.permanent is not None:
            text(self.permanent)


@dataclass(frozen=True)
class ObservedOrder:
    identity: ObservedIdentity
    contract: str
    instrument: InstrumentId
    side: OrderSide
    quantity: int
    order_type: str
    state: BrokerState
    filled: int | None
    remaining: int | None
    observed_at: datetime
    diagnostic: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ObservedIdentity) or not isinstance(self.instrument, InstrumentId):
            raise TypeError("typed identity and instrument required")
        if not isinstance(self.side, OrderSide) or not isinstance(self.state, BrokerState):
            raise TypeError("typed side and state required")
        text(self.contract)
        if self.order_type != "market":
            raise ValueError("unsupported order type")
        quantity(self.quantity, 1)
        timestamp(self.observed_at)
        if (self.filled is None) != (self.remaining is None):
            raise ValueError("partial quantity evidence")
        if self.filled is not None:
            quantity(self.filled)
            quantity(self.remaining)
            if self.filled + self.remaining > self.quantity:
                raise ValueError("inconsistent observed quantities")
            if self.state in {BrokerState.PENDING, BrokerState.WORKING, BrokerState.CANCEL_PENDING} and self.filled + self.remaining != self.quantity:
                raise ValueError("incomplete active order quantities")
            if self.state is BrokerState.FILLED and (self.filled != self.quantity or self.remaining):
                raise ValueError("inconsistent completion")


@dataclass(frozen=True)
class ObservedExecution:
    identity: ObservedIdentity
    execution_id: str
    contract: str
    instrument: InstrumentId
    side: OrderSide
    quantity: int
    price: Decimal
    executed_at: datetime
    observed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ObservedIdentity) or not isinstance(self.instrument, InstrumentId):
            raise TypeError("typed execution identity/instrument required")
        if not isinstance(self.side, OrderSide):
            raise TypeError("typed execution side required")
        text(self.execution_id)
        text(self.contract)
        quantity(self.quantity, 1)
        if not isinstance(self.price, Decimal) or not self.price.is_finite() or self.price <= 0:
            raise ValueError("invalid execution price")
        timestamp(self.executed_at)
        timestamp(self.observed_at)
        if self.executed_at > self.observed_at:
            raise ValueError("execution is in the future")


@dataclass(frozen=True)
class BrokerSnapshot:
    query_id: str
    account: str
    generation: str
    observed_at: datetime
    orders: tuple[ObservedOrder, ...]
    executions: tuple[ObservedExecution, ...]
    complete: bool
    diagnostic: str = ""

    def __post_init__(self) -> None:
        for value in (self.query_id, self.account, self.generation):
            text(value)
        timestamp(self.observed_at)
        if type(self.complete) is not bool or type(self.orders) is not tuple or type(self.executions) is not tuple:
            raise TypeError("immutable snapshot required")
        for values, cls in ((self.orders, ObservedOrder), (self.executions, ObservedExecution)):
            for item in values:
                if not isinstance(item, cls):
                    raise TypeError("invalid snapshot item")
                if item.identity.account != self.account or item.identity.generation != self.generation:
                    raise ValueError("snapshot scope mismatch")
                if item.observed_at > self.observed_at:
                    raise ValueError("snapshot predates observation")


@dataclass(frozen=True)
class OwnedIdentity:
    local_id: ClientOrderId
    identity: ObservedIdentity
    contract: str


class MatchStatus(str, Enum):
    MATCHED = "matched"
    BROKER_ONLY = "broker_only"
    LOCAL_ONLY = "local_only"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MatchResult:
    status: MatchStatus
    local_id: ClientOrderId | None
    broker_identity: ObservedIdentity | None
    reason: str
    execution_id: str | None = None


@dataclass(frozen=True)
class ReconciliationReport:
    snapshot: BrokerSnapshot
    local_versions: tuple[tuple[ClientOrderId, int], ...]
    results: tuple[MatchResult, ...]

    @property
    def matched(self) -> bool:
        return self.snapshot.complete and all(r.status is MatchStatus.MATCHED for r in self.results)


def reconcile_snapshot(snapshot: BrokerSnapshot, orders: tuple[ExecutionOrder, ...],
                       ownership: tuple[OwnedIdentity, ...]) -> ReconciliationReport:
    """Pure strong-identity matching; never update lifecycle, claim or economics.

    perm identity 跨会话有效；API identity 仅同 generation 有效。弱字段不能认领。
    """
    from execution.models import TERMINAL_EXECUTION_STATES

    local = {o.client_order_id: o for o in orders}
    results: list[MatchResult] = []
    seen: set[ClientOrderId] = set()
    owners_per_order: dict[ClientOrderId, set[ObservedIdentity]] = {}
    if not snapshot.complete:
        results.append(MatchResult(MatchStatus.UNKNOWN, None, None, "INCOMPLETE_QUERY:" + snapshot.diagnostic))
    for item in (*snapshot.orders, *snapshot.executions):
        identity = item.identity
        candidates = [b for b in ownership if b.identity.account == identity.account and (
            (identity.permanent is not None and b.identity.permanent == identity.permanent)
            or (b.identity.generation == identity.generation and b.identity.client == identity.client
                and b.identity.api_order == identity.api_order))]
        ids = {b.local_id for b in candidates}
        eid = item.execution_id if isinstance(item, ObservedExecution) else None
        cid = next(iter(ids)) if len(ids) == 1 else None
        status, reason = MatchStatus.MATCHED, "STRONG_IDENTITY"
        if len(ids) > 1:
            status, reason = MatchStatus.CONFLICT, "AMBIGUOUS_OWNERSHIP"
            if isinstance(item, ObservedOrder):
                seen.update(ids)
        elif not ids:
            status, reason = MatchStatus.BROKER_ONLY, "NO_DURABLE_OWNER"
        elif cid not in local:
            status, reason = MatchStatus.CONFLICT, "OWNER_WITHOUT_LOCAL_ORDER"
        else:
            order = local[cid]
            if isinstance(item, ObservedOrder):
                seen.add(cid)
            request = order.request
            if (any(b.contract != item.contract for b in candidates)
                    or request.instrument != item.instrument or request.side != item.side
                    or any(b.identity.permanent is not None and identity.permanent is not None
                           and b.identity.permanent != identity.permanent for b in candidates)
                    or (order.broker_order_id is not None and identity.permanent != order.broker_order_id.value)):
                status, reason = MatchStatus.CONFLICT, "IDENTITY_OR_CONTRACT_CONFLICT"
            elif order.updated_at.tzinfo is None or snapshot.observed_at < order.updated_at:
                status, reason = MatchStatus.UNKNOWN, "STALE_OR_UNCOMPARABLE_EVIDENCE"
            elif isinstance(item, ObservedOrder):
                owners_per_order.setdefault(cid, set()).add(identity)
                if request.quantity != item.quantity:
                    status, reason = MatchStatus.CONFLICT, "REQUEST_QUANTITY_CONFLICT"
                elif order.state in TERMINAL_EXECUTION_STATES:
                    status, reason = MatchStatus.CONFLICT, "TERMINAL_LOCAL_OPEN_BROKER"
                elif item.state is BrokerState.UNKNOWN or item.filled is None:
                    status, reason = MatchStatus.UNKNOWN, "INCOMPLETE_ORDER_STATE"
                elif item.filled != order.cumulative_filled_quantity:
                    status, reason = MatchStatus.UNKNOWN, "ECONOMIC_EVIDENCE_REQUIRED"
                elif item.state not in (BrokerState.WORKING, BrokerState.PENDING):
                    status, reason = MatchStatus.UNKNOWN, "EXPLICIT_STATE_REVIEW_REQUIRED"
                elif order.state.value == "cancel_pending":
                    status, reason = MatchStatus.UNKNOWN, "CANCEL_INTENT_REQUIRES_REVIEW"
            else:
                fills = [f for f in order.fills if f.broker_execution_id is not None
                         and f.broker_execution_id.value == eid]
                if not fills:
                    status, reason = MatchStatus.UNKNOWN, "FEE_COMPLETE_FILL_REQUIRED"
                elif len(fills) != 1 or (fills[0].fill.quantity != item.quantity
                        or fills[0].fill.price != item.price or fills[0].fill.filled_at != item.executed_at):
                    status, reason = MatchStatus.CONFLICT, "EXECUTION_ECONOMICS_CONFLICT"
        results.append(MatchResult(status, cid, identity, reason, eid))
    for cid, identities in owners_per_order.items():
        if len(identities) > 1:
            results.append(MatchResult(MatchStatus.CONFLICT, cid, None, "MULTIPLE_BROKER_ORDERS"))
    for order in orders:
        if order.state not in TERMINAL_EXECUTION_STATES and order.client_order_id not in seen:
            status = MatchStatus.LOCAL_ONLY if snapshot.complete else MatchStatus.UNKNOWN
            results.append(MatchResult(status, order.client_order_id, None, "NO_OPEN_ORDER_EVIDENCE_NO_RESEND"))
    return ReconciliationReport(snapshot, tuple((o.client_order_id, o.version) for o in orders), tuple(results))
