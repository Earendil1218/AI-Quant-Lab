"""Normalize raw callbacks and pair actual commissions. / 归一化原始回调并配对实际佣金。"""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from threading import RLock

from broker.ibkr.errors import ErrorCategory, classify_error
from broker.ibkr.models import (
    CommissionEvent, ErrorEvent, EventSource, ExecutionEvent, IdentityRegistry,
    OpenOrderEvent, OrderBinding, SessionEvent, StatusEvent, execution_ids, integer,
)
from execution import ExecutionFill
from execution.observations import ExecutionObservation, ObservationKind as Kind
from trading import Fill


class IBKREventNormalizer:
    """One bounded session's event state, without economic accounting or persistence.

    同一 session 的内存配对状态；不重复实现 cumulative accounting，不负责恢复。
    Raw records remain available on transport; malformed/conflicting data raises visibly.
    Callers must retain unresolved results and stop dispatch until reviewed.
    """

    def __init__(self, registry: IdentityRegistry, generation: str, client_id: int) -> None:
        self.registry = registry
        self.generation = generation
        self.client_id = client_id
        self._executions: dict[str, ExecutionEvent] = {}
        self._commissions: dict[str, CommissionEvent] = {}
        self._lock = RLock()

    def normalize(self, event: OpenOrderEvent | StatusEvent | ExecutionEvent | CommissionEvent | ErrorEvent | SessionEvent
                  ) -> tuple[ExecutionObservation, ...]:
        """Return immutable neutral facts; no aggregate mutation or external calls.

        只接受当前 generation；重复内容可重放，身份冲突/修正/未知对象明确失败。
        """
        if event.generation != self.generation:
            raise ValueError("stale session generation.")
        with self._lock:
            if isinstance(event, OpenOrderEvent):
                return (self._open_order(event),)
            if isinstance(event, StatusEvent):
                return (self._status(event),)
            if isinstance(event, ExecutionEvent):
                return (self._execution(event),)
            if isinstance(event, CommissionEvent):
                return self._commission(event)
            if isinstance(event, ErrorEvent):
                return self._error(event)
            if isinstance(event, SessionEvent):
                return tuple(self._observation(binding, Kind.CONNECTION_LOST, event.observed_at,
                                               detail=event.detail)
                             for binding in self.registry.bindings())
            raise TypeError("unsupported raw event.")

    def _observation(self, binding: OrderBinding, kind: Kind, observed_at: datetime,
                     **kwargs: object) -> ExecutionObservation:
        return ExecutionObservation(binding.identity.client_order_id, binding.request, kind,
                                    observed_at, binding.identity.broker_order_id, **kwargs)

    def _open_order(self, event: OpenOrderEvent) -> ExecutionObservation:
        binding = self.registry.resolve(event.generation, event.client_id, event.order_id, 0, event.account)
        request = binding.request
        if (event.con_id != binding.con_id or event.symbol != request.instrument.symbol
                or event.sec_type != "STK" or event.currency != "USD"
                or event.side != request.side.name or event.order_type != "MKT"
                or integer(event.quantity, "quantity", minimum=1) != request.quantity
                or event.order_ref != binding.identity.client_order_id.value):
            raise ValueError("openOrder request/contract correlation mismatch.")
        binding = self.registry.resolve(event.generation, event.client_id, event.order_id, event.perm_id, event.account)
        kind = {"Submitted": Kind.WORKING, "Filled": Kind.COMPLETION,
                "Cancelled": Kind.CANCELLED, "ApiCancelled": Kind.CANCELLED,
                "PendingCancel": Kind.CANCEL_PENDING}.get(event.status, Kind.UNRESOLVED)
        return self._observation(binding, kind, event.observed_at, detail=f"broker open order: {event.status}")

    def _status(self, event: StatusEvent) -> ExecutionObservation:
        binding = self.registry.resolve(event.generation, event.client_id, event.order_id, 0)
        if event.source is EventSource.LOCAL:
            # 中文：高层 Trade 合成状态只作为信息，不能替代原始 broker 确认。
            # English: Synthetic Trade states are informational, never broker acknowledgement.
            return self._observation(binding, Kind.INFORMATION, event.observed_at, detail="local synthetic status")
        if event.source is not EventSource.BROKER:
            raise ValueError("unrecognized event source.")
        filled = integer(event.filled, "filled")
        remaining = integer(event.remaining, "remaining")
        if filled > binding.request.quantity or filled + remaining > binding.request.quantity:
            raise ValueError("broker status quantity exceeds order quantity.")
        if event.status == "Filled" and (filled != binding.request.quantity or remaining != 0):
            raise ValueError("Filled status has inconsistent quantities.")
        binding = self.registry.resolve(event.generation, event.client_id, event.order_id, event.perm_id)
        kinds = {
            "ApiPending": Kind.PENDING, "PendingSubmit": Kind.PENDING,
            "PreSubmitted": Kind.HELD, "Submitted": Kind.WORKING,
            "Filled": Kind.COMPLETION, "PendingCancel": Kind.CANCEL_PENDING,
            "Cancelled": Kind.CANCELLED, "ApiCancelled": Kind.CANCELLED,
            "Inactive": Kind.UNRESOLVED,
        }
        kind = kinds.get(event.status, Kind.UNRESOLVED)
        return self._observation(binding, kind, event.observed_at,
                                 reported_filled_quantity=filled, detail=f"broker status: {event.status}")

    def _execution(self, event: ExecutionEvent) -> ExecutionObservation:
        binding = self.registry.resolve(event.generation, event.client_id, event.order_id,
                                        0, event.account)
        request = binding.request
        if (event.con_id != binding.con_id or event.symbol != request.instrument.symbol
                or event.sec_type != "STK" or event.currency != "USD"
                or event.side != ("BOT" if request.side.name == "BUY" else "SLD")):
            raise ValueError("execution contract/side mismatch.")
        if not event.perm_id:
            raise ValueError("execution requires stable broker identity.")
        shares = integer(event.shares, "shares", minimum=1)
        if shares > request.quantity:
            raise ValueError("execution would overfill the order.")
        if (not isinstance(event.price, Decimal) or not event.price.is_finite() or event.price <= 0
                or event.price >= Decimal("1.7976931348623157E+308")):
            raise ValueError("execution price must be a finite positive Decimal.")
        event = replace(event, shares=shares)
        execution_ids(event.account, event.exec_id)
        previous = self._executions.get(event.exec_id)
        if previous is not None and replace(event, observed_at=previous.observed_at) != previous:
            raise ValueError("execution identity conflicts with different economics.")
        # 中文：修正 execId 不能当成另一次经济成交；本阶段不实现冲正账务。
        # English: Correction families are quarantined, not booked as additional executions.
        family, separator, revision = event.exec_id.rpartition(".")
        if separator and revision.isdigit():
            for known in self._executions:
                if known != event.exec_id and known.rpartition(".")[0] == family:
                    raise ValueError("execution correction requires manual reconciliation.")
        # 中文：先校验全部经济内容，再绑定 permId，避免无效 callback 污染身份索引。
        # English: Validate all economics before binding permId so invalid callbacks cannot poison identity.
        binding = self.registry.resolve(event.generation, event.client_id, event.order_id,
                                        event.perm_id, event.account)
        self._executions.setdefault(event.exec_id, event)
        if event.exec_id not in self._commissions:
            return self._observation(binding, Kind.EXECUTION_PENDING, event.observed_at,
                                     detail="execution received; commission unresolved")
        return self._paired(event.exec_id)

    def _commission(self, event: CommissionEvent) -> tuple[ExecutionObservation, ...]:
        if not event.exec_id or event.exec_id != event.exec_id.strip():
            raise ValueError("commission execId is required.")
        # 中文：UNSET_DOUBLE 是有限数，也必须拒绝；真实零佣金则允许。
        # English: UNSET_DOUBLE is finite but still missing data; an actual zero is valid.
        if (event.currency != "USD" or not isinstance(event.commission, Decimal)
                or not event.commission.is_finite() or event.commission < 0
                or event.commission >= Decimal("1.7976931348623157E+308")):
            raise ValueError("commission must be a known nonnegative USD amount.")
        previous = self._commissions.get(event.exec_id)
        if previous is not None and replace(event, observed_at=previous.observed_at) != previous:
            raise ValueError("commission identity conflicts; adjustment is unsupported.")
        self._commissions.setdefault(event.exec_id, event)
        return (self._paired(event.exec_id),) if event.exec_id in self._executions else ()

    def _paired(self, exec_id: str) -> ExecutionObservation:
        execution = self._executions[exec_id]
        commission = self._commissions[exec_id]
        binding = self.registry.get(self.registry.resolve(
            execution.generation, execution.client_id, execution.order_id,
            execution.perm_id, execution.account).identity.client_order_id)
        bid, fid = execution_ids(execution.account, exec_id)
        economic = Fill(binding.request.instrument, binding.request.side, execution.shares,
                        execution.execution_time, execution.price, commission.commission)
        fill = ExecutionFill(binding.identity.client_order_id, fid, economic, bid)
        return self._observation(binding, Kind.FILL, max(execution.observed_at, commission.observed_at),
                                 execution_fill=fill)

    def _error(self, event: ErrorEvent) -> tuple[ExecutionObservation, ...]:
        category, kind = classify_error(event.code)
        if category is ErrorCategory.CONNECTION:
            return tuple(self._observation(binding, kind, event.observed_at, detail=category.value)
                         for binding in self.registry.bindings())
        try:
            binding = self.registry.resolve(event.generation, self.client_id, event.request_id, 0)
        except KeyError:
            # 中文：查询错误不能猜测关联到订单；原始诊断仍由 transport 保留。
            # English: Uncorrelated request errors cannot reject an order; raw diagnostics remain.
            return ()
        return (self._observation(binding, kind, event.observed_at,
                                  detail=f"{category.value}: {event.message}"),)
