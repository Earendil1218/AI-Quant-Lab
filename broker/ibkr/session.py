"""Explicit read-only session lifecycle; READY never unlocks order transport.

连接、观察、核对是独立步骤；重连使用新 transport，无自动重试。
"""

from enum import Enum
from typing import Protocol

from broker.ibkr.config import PaperExecutionConfig, PaperSafetyError
from broker.ibkr.observation import RawBrokerSnapshot, map_snapshot
from broker.ibkr.transport import SessionEvidence
from execution.broker_state import BrokerSnapshot, ReconciliationReport


class SessionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    READY = "ready"
    DEGRADED = "degraded"


class ObservationTransport(Protocol):
    generation: str

    def connect_readonly(self, *, integration_opt_in: bool = False) -> None: ...
    def evidence(self) -> SessionEvidence: ...
    def query_snapshot(self) -> RawBrokerSnapshot: ...
    def close(self) -> None: ...


class PaperObservationSession:
    """Dependency-injected one-shot session, not a scheduler or sender.

    账户 allowlist 依赖部署方独立确认；端口或账户前缀不能证明 Paper。
    """

    def __init__(self, config: PaperExecutionConfig, transport: ObservationTransport):
        self.config = config
        self.transport = transport
        self.generation = transport.generation
        self._state = SessionState.DISCONNECTED
        self.snapshot: BrokerSnapshot | None = None

    @property
    def state(self) -> SessionState:
        if self._state in {SessionState.CONNECTED, SessionState.READY}:
            try:
                self.validate()
            except PaperSafetyError:
                self._state = SessionState.DEGRADED
        return self._state

    def validate(self) -> None:
        self.config.validate(side_effect=False)
        self.transport.evidence().validate(self.config, self.generation)

    def connect(self, *, integration_opt_in: bool = False) -> None:
        if self._state is not SessionState.DISCONNECTED:
            raise PaperSafetyError("new session required for reconnect")
        self._state = SessionState.CONNECTING
        try:
            self.config.validate(side_effect=False)
            self.transport.connect_readonly(integration_opt_in=integration_opt_in)
            self.validate()
            self._state = SessionState.CONNECTED
        except Exception:
            self._state = SessionState.DEGRADED
            self.transport.close()
            raise

    def observe(self) -> BrokerSnapshot:
        if self.state is not SessionState.CONNECTED:
            raise PaperSafetyError("connected unreconciled session required")
        try:
            raw = self.transport.query_snapshot()
            self.validate()
            snapshot = map_snapshot(raw)
            if snapshot.account != self.config.account or snapshot.generation != self.generation:
                raise PaperSafetyError("query account/generation mismatch")
            self.snapshot = snapshot
            return snapshot
        except Exception:
            self._state = SessionState.DEGRADED
            raise

    def reconciled(self, report: ReconciliationReport, *, blocked: bool) -> None:
        self.validate()
        if self._state is not SessionState.CONNECTED or self.snapshot != report.snapshot:
            raise PaperSafetyError("report does not belong to this connected query")
        self._state = SessionState.READY if report.matched and not blocked else SessionState.DEGRADED

    def degrade(self) -> None:
        self._state = SessionState.DEGRADED

    def close(self) -> None:
        self.transport.close()
        self._state = SessionState.DEGRADED  # Never reuse a retired generation.
