"""IBKR raw snapshots to neutral evidence, without claiming foreign orders.

仅支持已确认账户的 STK/USD/MKT；未知状态保留为 UNKNOWN，非法数据拒绝。
"""

from dataclasses import dataclass, replace
from datetime import datetime

from broker.ibkr.models import (OpenOrderEvent, StatusEvent, ExecutionEvent, EventSource,
                               integer, execution_ids)
from broker.ibkr.recovery import BROKER_CODEC
from execution.broker_state import (BrokerSnapshot, BrokerState, ObservedIdentity,
                                    ObservedOrder, ObservedExecution, OwnedIdentity)
from trading import InstrumentId, AssetClass, OrderSide


@dataclass(frozen=True)
class RawBrokerSnapshot:
    query_id: str
    generation: str
    account: str
    observed_at: datetime
    orders: tuple[OpenOrderEvent, ...]
    statuses: tuple[StatusEvent, ...]
    executions: tuple[ExecutionEvent, ...]
    complete: bool
    diagnostic: str = ""


def identity(event: OpenOrderEvent | ExecutionEvent) -> ObservedIdentity:
    perm = integer(event.perm_id, "perm_id")
    return ObservedIdentity(event.account, event.generation,
                           str(integer(event.client_id, "client_id")),
                           str(integer(event.order_id, "order_id", minimum=1)),
                           f"ibkr:{len(event.account)}:{event.account}:perm:{perm}" if perm else None)


def contract(event: OpenOrderEvent | ExecutionEvent) -> tuple[str, InstrumentId]:
    if event.sec_type != "STK" or event.currency != "USD":
        raise ValueError("unsupported contract; only STK/USD observations")
    if not isinstance(event.symbol, str) or not event.symbol or event.symbol != event.symbol.strip().upper():
        raise ValueError("noncanonical symbol")
    return str(integer(event.con_id, "con_id", minimum=1)), InstrumentId(AssetClass.EQUITY, event.symbol)


def owned_identities(payloads: tuple[str, ...]) -> tuple[OwnedIdentity, ...]:
    """Project persisted broker mappings; never infer ownership from weak fields.

    跨会话扫描持久化映射，只投影身份，不更新 registry 或 local state。
    """
    result = []
    for payload in payloads:
        binding = BROKER_CODEC.loads(payload)
        saved = binding.identity
        neutral = ObservedIdentity(saved.account, saved.session_generation, str(saved.client_id),
                                   str(saved.order_id), None if saved.broker_order_id is None else saved.broker_order_id.value)
        result.append(OwnedIdentity(saved.client_order_id, neutral, str(binding.con_id)))
    return tuple(result)


def map_snapshot(raw: RawBrokerSnapshot) -> BrokerSnapshot:
    """Deterministic normalization with exact duplicate collapse.

    同一查询内重复 callback 去重；冲突 callback 拒绝，不选择最后一条。
    """
    if not isinstance(raw, RawBrokerSnapshot):
        raise TypeError("RawBrokerSnapshot required")
    if type(raw.complete) is not bool:
        raise TypeError("explicit boolean query completeness required")
    for values, cls in ((raw.orders, OpenOrderEvent), (raw.statuses, StatusEvent), (raw.executions, ExecutionEvent)):
        if type(values) is not tuple or any(not isinstance(event, cls) for event in values):
            raise TypeError("typed immutable callback sequence required")
    statuses = {}
    for event in raw.statuses:
        if event.generation != raw.generation or event.source is not EventSource.BROKER:
            raise ValueError("stale or synthetic status")
        if event.observed_at > raw.observed_at:
            raise ValueError("future status")
        key = integer(event.client_id, "client_id"), integer(event.order_id, "order_id", minimum=1)
        value = (integer(event.perm_id, "perm_id"), event.status,
                 integer(event.filled, "filled"), integer(event.remaining, "remaining"))
        if key in statuses and statuses[key] != value:
            raise ValueError("conflicting status callbacks in query")
        statuses[key] = value
    states = {"ApiPending": BrokerState.PENDING, "PendingSubmit": BrokerState.PENDING,
              "PreSubmitted": BrokerState.PENDING, "Submitted": BrokerState.WORKING,
              "PendingCancel": BrokerState.CANCEL_PENDING, "Cancelled": BrokerState.CANCELLED,
              "ApiCancelled": BrokerState.CANCELLED, "Filled": BrokerState.FILLED}
    orders, executions = {}, {}
    for event in raw.orders:
        if event.order_type != "MKT" or event.side not in {"BUY", "SELL"}:
            raise ValueError("unsupported order type/side")
        cid, instrument = contract(event)
        status = statuses.get((event.client_id, event.order_id))
        if status is not None and (status[0] != event.perm_id or status[1] != event.status):
            raise ValueError("openOrder/orderStatus conflict")
        item = ObservedOrder(identity(event), cid, instrument, OrderSide(event.side.lower()),
                             integer(event.quantity, "quantity", minimum=1), "market",
                             states.get(event.status, BrokerState.UNKNOWN),
                             None if status is None else status[2], None if status is None else status[3],
                             event.observed_at, "UNRECOGNIZED_STATUS:" + event.status if event.status not in states else "")
        # Receipt time is not a new economic fact. / 到达时间不同不制造新经济事实。
        key = item.identity
        if key in orders and replace(orders[key], observed_at=item.observed_at) != item:
            raise ValueError("conflicting openOrder callbacks")
        if key not in orders or item.observed_at < orders[key].observed_at:
            orders[key] = item
    for event in raw.executions:
        if event.side not in {"BOT", "SLD"}:
            raise ValueError("unknown execution side")
        cid, instrument = contract(event)
        item = ObservedExecution(identity(event), execution_ids(event.account, event.exec_id)[0].value,
                                 cid, instrument, OrderSide.BUY if event.side == "BOT" else OrderSide.SELL,
                                 integer(event.shares, "shares", minimum=1), event.price,
                                 event.execution_time, event.observed_at)
        if item.execution_id in executions and replace(executions[item.execution_id], observed_at=item.observed_at) != item:
            raise ValueError("conflicting execution callbacks")
        if item.execution_id not in executions or item.observed_at < executions[item.execution_id].observed_at:
            executions[item.execution_id] = item
    orphan_status = set(statuses) - {(e.client_id, e.order_id) for e in raw.orders}
    return BrokerSnapshot(raw.query_id, raw.account, raw.generation, raw.observed_at,
                          tuple(sorted(orders.values(), key=lambda o: repr(o.identity))),
                          tuple(executions[k] for k in sorted(executions)), raw.complete and not orphan_status,
                          "UNPAIRED_STATUS" if orphan_status else raw.diagnostic)
