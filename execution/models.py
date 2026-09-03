"""Broker-neutral execution lifecycle records. / 与 broker 无关的执行生命周期记录。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TypeVar
from uuid import uuid4

from trading.fills import Fill
from trading.orders import OrderRequest


@dataclass(frozen=True)
class _StringIdentity:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError("identity value must be a string.")
        normalized = self.value.strip()
        if not normalized:
            raise ValueError("identity value must not be empty.")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ClientOrderId(_StringIdentity):
    """Stable identity assigned by this system. / 本系统分配的稳定订单身份。"""

    @classmethod
    def generate(cls) -> ClientOrderId:
        return cls(str(uuid4()))


@dataclass(frozen=True)
class BrokerOrderId(_StringIdentity):
    pass


@dataclass(frozen=True)
class BrokerExecutionId(_StringIdentity):
    pass


@dataclass(frozen=True)
class ExecutionFillId(_StringIdentity):
    pass


class ExecutionOrderState(str, Enum):
    CREATED = "created"
    AUTHORIZED = "authorized"
    SUBMISSION_PENDING = "submission_pending"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


TERMINAL_EXECUTION_STATES = frozenset(
    {ExecutionOrderState.FILLED, ExecutionOrderState.CANCELLED, ExecutionOrderState.REJECTED}
)


@dataclass(frozen=True)
class SubmissionAuthorization:
    client_order_id: ClientOrderId
    request: OrderRequest
    authorized_at: datetime
    authorized_by: str

    def __post_init__(self) -> None:
        _require_type("client_order_id", self.client_order_id, ClientOrderId)
        _require_type("request", self.request, OrderRequest)
        _require_type("authorized_at", self.authorized_at, datetime)
        if not isinstance(self.authorized_by, str):
            raise TypeError("authorized_by must be a string.")
        authority = self.authorized_by.strip()
        if not authority:
            raise ValueError("authorized_by must not be empty.")
        object.__setattr__(self, "authorized_by", authority)


@dataclass(frozen=True)
class ExecutionFill:
    client_order_id: ClientOrderId
    fill_id: ExecutionFillId
    fill: Fill
    broker_execution_id: BrokerExecutionId | None = None

    def __post_init__(self) -> None:
        _require_type("client_order_id", self.client_order_id, ClientOrderId)
        _require_type("fill_id", self.fill_id, ExecutionFillId)
        _require_type("fill", self.fill, Fill)
        if self.broker_execution_id is not None:
            _require_type("broker_execution_id", self.broker_execution_id, BrokerExecutionId)


@dataclass(frozen=True)
class BrokerRejection:
    client_order_id: ClientOrderId
    rejected_at: datetime
    code: str | None
    message: str

    def __post_init__(self) -> None:
        _require_type("client_order_id", self.client_order_id, ClientOrderId)
        _require_type("rejected_at", self.rejected_at, datetime)
        if self.code is not None and not isinstance(self.code, str):
            raise TypeError("code must be a string or None.")
        if not isinstance(self.message, str):
            raise TypeError("message must be a string.")
        message = self.message.strip()
        if not message:
            raise ValueError("message must not be empty.")
        object.__setattr__(self, "message", message)


@dataclass(frozen=True)
class ExecutionOrder:
    client_order_id: ClientOrderId
    request: OrderRequest
    state: ExecutionOrderState
    created_at: datetime
    updated_at: datetime
    broker_order_id: BrokerOrderId | None = None
    cumulative_filled_quantity: int = 0
    version: int = 0
    fills: tuple[ExecutionFill, ...] = ()
    authorization: SubmissionAuthorization | None = None
    broker_rejection: BrokerRejection | None = None

    def __post_init__(self) -> None:
        _require_type("client_order_id", self.client_order_id, ClientOrderId)
        _require_type("request", self.request, OrderRequest)
        _require_type("state", self.state, ExecutionOrderState)
        _require_type("created_at", self.created_at, datetime)
        _require_type("updated_at", self.updated_at, datetime)
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at.")
        if self.broker_order_id is not None:
            _require_type("broker_order_id", self.broker_order_id, BrokerOrderId)
        _require_non_negative_int("cumulative_filled_quantity", self.cumulative_filled_quantity)
        _require_non_negative_int("version", self.version)
        if self.cumulative_filled_quantity > self.request.quantity:
            raise ValueError("cumulative filled quantity cannot exceed order quantity.")
        if not isinstance(self.fills, tuple) or any(
            not isinstance(fill, ExecutionFill) for fill in self.fills
        ):
            raise TypeError("fills must be a tuple of ExecutionFill values.")
        if sum(fill.fill.quantity for fill in self.fills) > self.cumulative_filled_quantity:
            raise ValueError("recorded fills cannot exceed cumulative_filled_quantity.")
        if any(fill.client_order_id != self.client_order_id for fill in self.fills):
            raise ValueError("all fills must bind the execution ClientOrderId.")
        fill_ids = [fill.fill_id for fill in self.fills]
        if len(fill_ids) != len(set(fill_ids)):
            raise ValueError("fill identities must be unique within an execution order.")
        broker_execution_ids = [
            fill.broker_execution_id
            for fill in self.fills
            if fill.broker_execution_id is not None
        ]
        if len(broker_execution_ids) != len(set(broker_execution_ids)):
            raise ValueError("broker execution identities must be unique.")
        if self.authorization is not None:
            _require_type("authorization", self.authorization, SubmissionAuthorization)
            if (
                self.authorization.client_order_id != self.client_order_id
                or self.authorization.request != self.request
            ):
                raise ValueError("authorization must bind this execution order.")
        if self.state is ExecutionOrderState.CREATED and self.authorization is not None:
            raise ValueError("a CREATED order cannot already be authorized.")
        if self.state is not ExecutionOrderState.CREATED and self.authorization is None:
            raise ValueError("post-creation execution state requires authorization.")
        if self.state is ExecutionOrderState.FILLED and self.remaining_quantity != 0:
            raise ValueError("FILLED state requires the complete order quantity.")
        if self.state is ExecutionOrderState.PARTIALLY_FILLED and not (
            0 < self.cumulative_filled_quantity < self.request.quantity
        ):
            raise ValueError("PARTIALLY_FILLED requires an incomplete positive quantity.")
        if self.broker_rejection is not None:
            _require_type("broker_rejection", self.broker_rejection, BrokerRejection)

    @property
    def remaining_quantity(self) -> int:
        return self.request.quantity - self.cumulative_filled_quantity


@dataclass(frozen=True)
class BrokerOrderObservation:
    client_order_id: ClientOrderId
    state: ExecutionOrderState
    observed_at: datetime
    broker_order_id: BrokerOrderId | None = None
    cumulative_filled_quantity: int = 0

    def __post_init__(self) -> None:
        _require_type("client_order_id", self.client_order_id, ClientOrderId)
        _require_type("state", self.state, ExecutionOrderState)
        _require_type("observed_at", self.observed_at, datetime)
        if self.broker_order_id is not None:
            _require_type("broker_order_id", self.broker_order_id, BrokerOrderId)
        _require_non_negative_int(
            "cumulative_filled_quantity", self.cumulative_filled_quantity
        )


@dataclass(frozen=True)
class BrokerFillObservation:
    execution_fill: ExecutionFill
    observed_at: datetime

    def __post_init__(self) -> None:
        _require_type("execution_fill", self.execution_fill, ExecutionFill)
        _require_type("observed_at", self.observed_at, datetime)


class ReconciliationIssueKind(str, Enum):
    LOCAL_ORDER_MISSING_AT_BROKER = "local_order_missing_at_broker"
    BROKER_ORDER_UNKNOWN_LOCALLY = "broker_order_unknown_locally"
    STATE_MISMATCH = "state_mismatch"
    FILL_QUANTITY_MISMATCH = "fill_quantity_mismatch"
    DUPLICATE_FILL = "duplicate_fill"
    UNRESOLVED_SUBMISSION = "unresolved_submission"


@dataclass(frozen=True)
class ReconciliationIssue:
    kind: ReconciliationIssueKind
    client_order_id: ClientOrderId
    detail: str

    def __post_init__(self) -> None:
        _require_type("kind", self.kind, ReconciliationIssueKind)
        _require_type("client_order_id", self.client_order_id, ClientOrderId)
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise ValueError("detail must be a non-empty string.")


@dataclass(frozen=True)
class ReconciliationResult:
    issues: tuple[ReconciliationIssue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.issues, tuple) or any(
            not isinstance(issue, ReconciliationIssue) for issue in self.issues
        ):
            raise TypeError("issues must be a tuple of ReconciliationIssue values.")

    @property
    def is_consistent(self) -> bool:
        return not self.issues


T = TypeVar("T")


def _require_type(name: str, value: object, expected: type[T]) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{name} must be a {expected.__name__}.")


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer (bool is not accepted).")
    if value < 0:
        raise ValueError(f"{name} must not be negative.")
