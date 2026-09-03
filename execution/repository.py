"""Execution persistence boundary and offline in-memory implementation."""

from __future__ import annotations

from typing import Protocol

from execution.models import ClientOrderId, ExecutionOrder


class ExecutionOrderRepository(Protocol):
    def add(self, order: ExecutionOrder) -> None: ...

    def get(self, client_order_id: ClientOrderId) -> ExecutionOrder | None: ...

    def save(self, order: ExecutionOrder, expected_version: int) -> None: ...


class InMemoryExecutionOrderRepository:
    """Offline store with no crash or restart durability. / 不提供崩溃或重启持久性。"""

    def __init__(self) -> None:
        self._orders: dict[ClientOrderId, ExecutionOrder] = {}

    def add(self, order: ExecutionOrder) -> None:
        _require_order(order)
        if order.client_order_id in self._orders:
            raise ValueError("ClientOrderId already exists.")
        self._orders[order.client_order_id] = order

    def get(self, client_order_id: ClientOrderId) -> ExecutionOrder | None:
        if not isinstance(client_order_id, ClientOrderId):
            raise TypeError("client_order_id must be a ClientOrderId.")
        return self._orders.get(client_order_id)

    def save(self, order: ExecutionOrder, expected_version: int) -> None:
        _require_order(order)
        if isinstance(expected_version, bool) or not isinstance(expected_version, int):
            raise TypeError("expected_version must be an integer.")
        current = self._orders.get(order.client_order_id)
        if current is None:
            raise KeyError("execution order does not exist.")
        if current.version != expected_version:
            raise ValueError("stale execution order version.")
        if order.version != expected_version + 1:
            raise ValueError("saved order must advance version by exactly one.")
        self._orders[order.client_order_id] = order


def _require_order(order: ExecutionOrder) -> None:
    if not isinstance(order, ExecutionOrder):
        raise TypeError("order must be an ExecutionOrder.")
