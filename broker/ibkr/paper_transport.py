"""Explicitly authorized Paper I/O on the existing raw callback boundary.

受控 Paper 副作用：只接受当前会话人工确认和同一数据库的持久化 claim/身份。
"""

from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from threading import RLock
from typing import Iterator, TYPE_CHECKING

from ib_insync import Contract, Order

from broker.ibkr.config import PaperExecutionConfig, PaperSafetyError
from broker.ibkr.mapping import EquityContractSpec, map_contract, map_order, validate_qualified
from broker.ibkr.models import IdentityRegistry
from broker.ibkr.recovery import PersistentIdentityRegistry
from broker.ibkr.transport import RawEvent, ReadOnlyIBKRTransport
from execution.adapter import DispatchOperation
from execution.dispatch import AttemptClaims
from execution.models import ClientOrderId, ExecutionOrder, ExecutionOrderState
from infrastructure.reconciliation import ReconciliationStore
from infrastructure.sqlite_execution import SQLiteAttemptClaims, SQLiteExecutionRepository
from trading import OrderRequest, OrderSide

if TYPE_CHECKING:
    from broker.ibkr.observation import RawBrokerSnapshot
    from execution.broker_state import ReconciliationReport


class PaperNotSentError(PaperSafetyError):
    """The real API entry was provably not reached."""


@dataclass(frozen=True)
class PaperSessionConfirmation:
    """Operator evidence, never inferred from DU, port or client ID.

    IBKR Socket API has no trusted account-type attestation. The operator must
    independently verify Simulated/Paper login and this exact account in TWS.
    人工确认必须绑定本次 generation；代码不能替用户制造确认。
    """

    generation: str
    account: str
    confirmed_by: str
    declaration: str

    def validate(self, config: PaperExecutionConfig, generation: str) -> None:
        if (self.generation != generation or self.account != config.account
                or not isinstance(self.confirmed_by, str) or not self.confirmed_by.strip()
                or self.declaration != "I verified this exact account is Simulated/Paper in TWS"):
            raise PaperSafetyError("current exact-account human Paper confirmation required")


class PaperExecutionTransport(ReadOnlyIBKRTransport):
    """One owned generation; no reconnect, resend, ambient authority or real cancel.

    显式连接授权与副作用授权分离；构造不连接。只读 transport 完全不变。
    Paper identity depends on truthful independent operator confirmation, not a
    broker-provided account-type proof. Never use an unverified allowlist.
    """

    def __init__(self, config: PaperExecutionConfig) -> None:
        super().__init__(config)
        self._expected_config = replace(config)
        self._expected_generation = self.generation
        self._dispatch_lock = RLock()
        self._retired = False
        self._confirmation: PaperSessionConfirmation | None = None
        self._side_effect_opt_in = False
        self._active: tuple[ExecutionOrder, AttemptClaims, IdentityRegistry, PaperExecutionConfig, EquityContractSpec] | None = None
        self._entered: set[ClientOrderId] = set()
        self._reconciled_repository = None
        self._retained_events: tuple[RawEvent, ...] = ()
        self._ib.errorEvent += self._on_error

    def connect_paper(self, confirmation: PaperSessionConfirmation, *,
                      integration_opt_in: bool = False,
                      side_effect_opt_in: bool = False) -> None:
        """Explicit double opt-in; confirmation must be supplied by the operator.

        不读取环境生成权限，不关闭 TWS Read-Only 设置，不自动重连。
        """
        with self._dispatch_lock:
            if integration_opt_in is not True or side_effect_opt_in is not True:
                raise PaperSafetyError("explicit integration AND Paper side-effect opt-in required")
            if type(confirmation) is not PaperSessionConfirmation:
                raise PaperSafetyError("explicit operator Paper confirmation required")
            self._validate_configuration()
            confirmation.validate(self._expected_config, self._expected_generation)
            if self._connected_once or self._retired:
                raise PaperSafetyError("retired session cannot reconnect")
            self._connected_once = True
            try:
                self._ib.connect(self.config.host, self.config.port, clientId=self.config.client_id,
                                 readonly=False, account=self.config.account, timeout=10)
                if self._retired:
                    raise PaperSafetyError("session was lost during connection; new generation required")
                self._valid = True
                self.evidence().validate(self._expected_config, self._expected_generation)
                self._confirmation = confirmation
                self._side_effect_opt_in = True
            except BaseException:
                self.close()
                raise

    def _on_disconnected(self) -> None:
        self._retired = True
        super()._on_disconnected()

    def _on_error(self, request_id, code, message, contract) -> None:
        from broker.ibkr.errors import ErrorCategory, classify_error
        if classify_error(code)[0] in {ErrorCategory.CONNECTION, ErrorCategory.UNKNOWN}:
            # Loss or unclassified diagnostics retire this generation even while
            # the local socket is connected; recovery notices cannot restore it.
            self._valid = False
            self._retired = True

    def _validate_configuration(self) -> None:
        self._expected_config.validate(side_effect=True)
        # Additional identifier restriction, never a substitute for independently
        # verified allowlist, human confirmation and current session evidence.
        if not self._expected_config.account.startswith("DU"):
            raise PaperSafetyError("only independently verified DU Paper accounts are supported")
        if self.config != self._expected_config or self.generation != self._expected_generation:
            raise PaperSafetyError("execution configuration/generation changed")

    def _session_preflight(self) -> None:
        self._validate_configuration()
        if self._retired:
            raise PaperSafetyError("retired session generation cannot regain authority")
        if self._side_effect_opt_in is not True or self._confirmation is None:
            raise PaperSafetyError("Paper transport is locked without explicit opt-in")
        self._confirmation.validate(self._expected_config, self._expected_generation)
        self.evidence().validate(self._expected_config, self._expected_generation)

    @contextmanager
    def _dispatch_scope(self, order: ExecutionOrder, claims: AttemptClaims,
                        registry: IdentityRegistry, config: PaperExecutionConfig,
                        spec: EquityContractSpec) -> Iterator[None]:
        """Serialize revalidation/claim/identity/send in one owned transport scope.

        资格查询之前不领取 claim；scope 不是可复制/持久化的发送令牌。
        """
        with self._dispatch_lock:
            if self._active is not None:
                raise PaperSafetyError("nested dispatch is forbidden")
            # Re-entry with a previously consumed attempt must be rejected before
            # an internal scope can use verify_current as a send capability.
            claims.validate(order, DispatchOperation.SUBMIT)
            self._active = (order, claims, registry, config, spec)
            try:
                yield
            finally:
                self._active = None

    def preflight(self) -> None:
        self._session_preflight()
        if self._active is None:
            raise PaperSafetyError("durable adapter dispatch scope required")
        order, claims, registry, config, spec = self._active
        if type(order.request) is not OrderRequest or order.request.side is not OrderSide.BUY:
            raise PaperSafetyError("only exact BUY requests are supported; real Paper SELL is locked")
        # Repeat the non-consuming mapping constraint at the real I/O boundary;
        # callers cannot substitute a spec for a different approved instrument.
        map_contract(order.request.instrument, spec)
        if (config != self._expected_config or not isinstance(claims, SQLiteAttemptClaims)
                or not isinstance(registry, PersistentIdentityRegistry)
                or registry.generation != self._expected_generation
                or registry.repository.path != claims.repository.path):
            raise PaperSafetyError("same-database durable claim and ownership required")
        if self.has_pending_callbacks:
            raise PaperSafetyError("pending raw callbacks require durable ingestion")
        repo = claims.repository
        if self._reconciled_repository != repo.path:
            raise PaperSafetyError("fresh startup reconciliation for this database required")
        # A risk PASS alone is insufficient: require the persisted planning ticket
        # and the independently supplied SubmissionAuthorization on its intent.
        repo.validate_planned(order.client_order_id)
        if (ReconciliationStore(repo).blocked() or repo.unresolved_observations()
                or repo.pending_inbox_count() or repo.pending_accounting_count()):
            raise PaperSafetyError("unresolved durable evidence blocks Paper dispatch")
        for candidate in repo.list_recovery_candidates():
            if (candidate.order.client_order_id != order.client_order_id
                    or candidate.order.state is not ExecutionOrderState.SUBMISSION_PENDING):
                raise PaperSafetyError("recovery review required before Paper dispatch")

    def accept_reconciliation(self, report: "ReconciliationReport",
                              repository: SQLiteExecutionRepository) -> None:
        """Bind readiness to persisted evidence from this exact session/database."""
        self._session_preflight()
        from infrastructure.reconciliation import CODEC, QUERIES, semantic_key
        store = ReconciliationStore(repository)
        persisted_query = report.snapshot in tuple(CODEC.loads(p) for p in repository.evidence(QUERIES))
        persisted_result = any(semantic_key(previous) == semantic_key(report) for previous in store.reports())
        if (report.snapshot.generation != self._expected_generation
                or report.snapshot.account != self._expected_config.account
                or not report.matched or not persisted_query or not persisted_result or store.blocked()):
            raise PaperSafetyError("persisted matching current-session reconciliation required")
        self._reconciled_repository = repository.path

    @property
    def has_pending_callbacks(self) -> bool:
        return bool(self._retained_events) or not self._events.empty()

    def retain_events(self, events: tuple[RawEvent, ...]) -> None:
        """Keep unpersisted raw records visible after an ingestion failure."""
        self._retained_events += tuple(events)

    def read_events(self) -> tuple[RawEvent, ...]:
        events, self._retained_events = self._retained_events, ()
        return events + super().read_events()

    def next_order_id(self) -> int:
        self.preflight()
        order, claims, _, _, _ = self._active
        claims.verify_current(order, DispatchOperation.SUBMIT)
        return self._ib.client.getReqId()

    def place(self, contract: Contract, order: Order) -> None:
        """Exactly one API entry after durable ownership and final validation.

        Returning is not broker acknowledgement. API-entry failures are UNKNOWN;
        proven pre-entry failures are NOT_SENT and never release the claim.
        """
        with self._dispatch_lock:
            try:
                self.preflight()
                pending, claims, registry, _, spec = self._active
                claims.verify_current(pending, DispatchOperation.SUBMIT)
                binding = registry.get(pending.client_order_id)
                identity = binding.identity
                validate_qualified(contract, spec)
                expected = map_order(pending.request, identity)
                if (binding.request != pending.request or binding.con_id != contract.conId
                        or identity.account != self._expected_config.account
                        or identity.client_id != self._expected_config.client_id
                        or identity.session_generation != self._expected_generation
                        or asdict(order) != asdict(expected)):
                    raise PaperSafetyError("prepared contract/order differs from durable ownership")
                key = pending.client_order_id
                if key in self._entered:
                    raise PaperSafetyError("place boundary already entered; resend forbidden")
            except Exception as exc:
                raise PaperNotSentError(str(exc)) from exc
            self._entered.add(key)
            try:
                self._ib.placeOrder(contract, order)
                # A synchronous disconnect is uncertainty even if the API returned.
                self._session_preflight()
            except Exception as exc:
                # Never let an API-thrown exception impersonate our pre-entry
                # NOT_SENT proof, even if it happens to use the same exception type.
                raise RuntimeError(f"placeOrder entered: {type(exc).__name__}: {exc}") from exc

    def query_snapshot(self) -> "RawBrokerSnapshot":
        """One explicitly requested fresh query; never a polling/reconnect loop.

        Explicit queries revalidate the current session; errors retire it.
        """
        with self._dispatch_lock:
            self._session_preflight()
            self._query_started = False
            try:
                return super().query_snapshot()
            except BaseException:
                self.close()
                raise

    def cancel(self, order: Order) -> None:
        """Real cancel remains locked until its durable lifecycle is reviewed.

        真实撤单仍锁闭；不把本地合成取消状态当作 broker 确认。
        """
        raise PaperSafetyError("Phase 3K real Paper cancellation is locked")

    def close(self) -> None:
        with self._dispatch_lock:
            self._retired = True
            self._side_effect_opt_in = False
            super().close()
