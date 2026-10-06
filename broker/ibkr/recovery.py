"""Durable offline callback evidence, never connection recovery or send authority.

持久化旧会话身份和原始回调；不连接、不重新认领订单、不恢复发送权限。
"""

from dataclasses import replace
import json

from broker.ibkr.errors import ErrorCategory, classify_error
from broker.ibkr.events import IBKREventNormalizer
from broker.ibkr.models import (
    CommissionEvent, ErrorEvent, EventSource, ExecutionEvent, IBKROrderIdentity,
    IdentityRegistry, OpenOrderEvent, OrderBinding, SessionEvent, StatusEvent, integer,
)
from infrastructure.codec import Codec


BROKER_CODEC = Codec((CommissionEvent, ErrorEvent, EventSource, ExecutionEvent,
                     IBKROrderIdentity, OpenOrderEvent, OrderBinding, SessionEvent, StatusEvent))


class PersistentIdentityRegistry(IdentityRegistry):
    """Persist binding before transport; rehydrate only the named old session.

    发送前保存 API 身份；恢复仅用于证据重放，不可跨 generation 发送。
    """

    def __init__(self, repository, generation: str):
        if not generation:
            raise ValueError("generation required")
        super().__init__()
        self.repository = repository
        self.generation = generation
        self.namespace = "ibkr-bindings:" + generation
        for payload in repository.evidence(self.namespace):
            super().register(BROKER_CODEC.loads(payload))

    def register(self, binding):
        if binding.identity.session_generation != self.generation:
            raise ValueError("session generation mismatch")
        with self._lock:
            candidate = self._copy_registry()
            candidate.register(binding)
            self._persist(binding)
            super().register(binding)

    def _persist(self, binding, *, previous=None):
        identity = binding.identity
        api_scope = json.dumps((identity.session_generation, identity.client_id), separators=(",", ":"))
        permanent = (("ibkr_perm", identity.account, str(identity.perm_id)),) if identity.perm_id else ()
        self.repository.put_evidence(self.namespace, identity.client_order_id.value, BROKER_CODEC.dumps(binding),
            expected_payload=None if previous is None else BROKER_CODEC.dumps(previous),
            scoped_identities=(("ibkr_api", api_scope, str(identity.order_id)),),
            permanent_identities=permanent)

    def _copy_registry(self):
        candidate = IdentityRegistry()
        for binding in super().bindings():
            candidate.register(binding)
        return candidate

    def resolve(self, generation, client_id, order_id, perm_id, account=None):
        with self._lock:
            candidate = self._copy_registry()
            binding = candidate.resolve(generation, client_id, order_id, perm_id, account)
            previous = super().get(binding.identity.client_order_id)
            self._persist(binding, previous=previous)
            return super().resolve(generation, client_id, order_id, perm_id, account)


class PersistentIBKRInbox:
    """Raw input commits before pairing; replay reconstructs commission gaps.

    原始事件先提交；重建已有 normalizer，不复制配对逻辑。异常记录保留并阻断重放。
    Replay returns neutral observations for the application's transactional consumer.
    """

    def __init__(self, repository, generation: str, client_id: int):
        self.repository = repository
        self.generation = generation
        self.client_id = client_id
        self.namespace = "ibkr-inbox:" + generation

    def append(self, event):
        """Persist without claiming that normalization/accounting succeeded.

        只保存，不声称已完成归一化或记账；调用方随后显式 replay。
        """
        if event.generation != self.generation:
            raise ValueError("stale session generation")
        # Broker float quantities are canonicalized only here, never in the money codec.
        # 仅在 broker 边界接受整数值 float；不支持小数股，不截断，不放宽金额 codec。
        if isinstance(event, ExecutionEvent):
            event = replace(event, shares=integer(event.shares, "shares", minimum=1))
        elif isinstance(event, StatusEvent):
            event = replace(event, filled=integer(event.filled, "filled"),
                            remaining=integer(event.remaining, "remaining"))
        elif isinstance(event, OpenOrderEvent):
            event = replace(event, quantity=integer(event.quantity, "quantity", minimum=1))
        self.repository.append_inbox(self.namespace, BROKER_CODEC.dumps(event))

    def replay(self):
        """Rebuild old-session facts without network access. / 离线重建旧会话事实。"""
        return self.replay_batch()[1]

    def replay_batch(self):
        """Snapshot the input boundary before replay. / 重放前固定输入范围。"""
        registry = PersistentIdentityRegistry(self.repository, self.generation)
        normalizer = IBKREventNormalizer(registry, self.generation, self.client_id)
        result = []
        entries = self.repository.inbox_entries(self.namespace)
        executions, commissions = set(), set()
        for _, payload in entries:
            event = BROKER_CODEC.loads(payload)
            if isinstance(event, ErrorEvent) and classify_error(event.code)[0] is ErrorCategory.UNKNOWN:
                # Replay must recreate the blocker after a crash between raw
                # persistence and normalization, before acknowledging the batch.
                from infrastructure.reconciliation import ReconciliationStore
                ReconciliationStore(self.repository).failure(self.generation, "UNCLASSIFIED_BROKER_DIAGNOSTIC")
            normalized = normalizer.normalize(event)
            if isinstance(event, ExecutionEvent):
                family, separator, revision = event.exec_id.rpartition(".")
                family = ("revision", family) if separator and revision.isdigit() else ("exact", event.exec_id)
                binding = registry.resolve(event.generation, event.client_id, event.order_id,
                                           event.perm_id, event.account)
                self.repository.claim_execution_family(
                    event.account, json.dumps(family, separators=(",", ":")), event.exec_id,
                    binding.identity.client_order_id)
                executions.add(event.exec_id)
            elif isinstance(event, CommissionEvent):
                commissions.add(event.exec_id)
            result.extend(normalized)
        return (entries[-1][0] if entries else 0), tuple(result), executions != commissions
