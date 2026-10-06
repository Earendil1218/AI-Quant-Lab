"""Atomic reconciliation evidence on the existing SQLite evidence seam.

复用 schema v2 evidence 表，不改写执行状态或记账；未知结果只追加、不自动解除。
"""

from dataclasses import replace
from hashlib import sha256
from datetime import datetime, timezone
from typing import Callable

from execution import broker_state as facts
from execution.broker_state import BrokerSnapshot, OwnedIdentity, ReconciliationReport, reconcile_snapshot
from infrastructure.codec import Codec
from infrastructure.sqlite_execution import SQLiteExecutionRepository, VersionConflict


TYPES = tuple(getattr(facts, name) for name in (
    "BrokerState", "ObservedIdentity", "ObservedOrder", "ObservedExecution", "BrokerSnapshot",
    "OwnedIdentity", "MatchStatus", "MatchResult", "ReconciliationReport"))
CODEC = Codec(TYPES)
REPORTS = "reconciliation-reports:v1"
QUERIES = "reconciliation-queries:v1"
FAILURES = "reconciliation-failures:v1"


def semantic_key(report: ReconciliationReport) -> str:
    """Receipt/query/session changes alone do not create another economic fact.

    稳定 permId 跨会话去重；没有 permId 时保留 session 身份，不猜测跨会话等价。
    """
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    def identity(value):
        if value is None or value.permanent is None:
            return value
        return replace(value, generation="stable", client="stable", api_order="stable")
    snapshot = report.snapshot
    orders = tuple(replace(o, identity=identity(o.identity), observed_at=epoch) for o in snapshot.orders)
    executions = tuple(replace(e, identity=identity(e.identity), observed_at=e.executed_at) for e in snapshot.executions)
    # Hash primitive tuples rather than fabricating a valid query snapshot.
    results = tuple(replace(r, broker_identity=identity(r.broker_identity)) for r in report.results)
    values = (snapshot.account, snapshot.complete, snapshot.diagnostic,
              tuple(sorted(orders, key=CODEC.dumps)), tuple(sorted(executions, key=CODEC.dumps)),
              report.local_versions, tuple(sorted(results, key=CODEC.dumps)))
    return sha256(CODEC.dumps(values).encode()).hexdigest()


class ReconciliationStore:
    def __init__(self, repository: SQLiteExecutionRepository):
        self.repository = repository

    def inputs(self):
        """Take one immutable local state/evidence view. / 同事务读取本地事实与身份映射。"""
        with self.repository._transaction() as db:
            orders = tuple(self.repository.codec.loads(row[0]) for row in db.execute(
                "SELECT payload FROM executions ORDER BY id"))
            bindings = tuple(row[0] for row in db.execute(
                "SELECT payload FROM evidence WHERE namespace LIKE 'ibkr-bindings:%' ORDER BY namespace,key"))
        return orders, bindings

    def reconcile(self, snapshot: BrokerSnapshot,
                  ownership_mapper: Callable[[tuple[str, ...]], tuple[OwnedIdentity, ...]]) -> ReconciliationReport:
        orders, bindings = self.inputs()
        report = reconcile_snapshot(snapshot, orders, ownership_mapper(bindings))
        # Identical facts across a fresh query retain one result; each query envelope
        # is separately bound to its exact input for freshness and audit.
        # 同事实重查不重复结果；query envelope 单独校验，禁止同 ID 偷换事实。
        payload = CODEC.dumps(report)
        key = semantic_key(report)
        with self.repository._transaction() as db:
            current = tuple(self.repository.codec.loads(row[0]) for row in db.execute(
                "SELECT payload FROM executions ORDER BY id"))
            current_bindings = tuple(row[0] for row in db.execute(
                "SELECT payload FROM evidence WHERE namespace LIKE 'ibkr-bindings:%' ORDER BY namespace,key"))
            if current != orders or current_bindings != bindings:
                raise VersionConflict("local facts changed during reconciliation")
            previous = db.execute("SELECT payload FROM evidence WHERE namespace=? AND key=?",
                                  (QUERIES, snapshot.query_id)).fetchone()
            query_payload = CODEC.dumps(snapshot)
            if previous is not None and previous[0] != query_payload:
                raise VersionConflict("query identity reused with different facts")
            db.execute("INSERT OR IGNORE INTO evidence VALUES(?,?,?)", (QUERIES, snapshot.query_id, query_payload))
            db.execute("INSERT OR IGNORE INTO evidence VALUES(?,?,?)", (REPORTS, key, payload))
        return report

    def failure(self, generation: str, diagnostic: str) -> None:
        # Only stable diagnostic codes, not arbitrary exception text/account details.
        # 不持久化可能含凭据的异常文本；失败永久阻断，后续需显式处置设计。
        with self.repository._transaction() as db:
            db.execute("INSERT OR IGNORE INTO evidence VALUES(?,?,?)", (
                FAILURES, generation, CODEC.dumps((generation, diagnostic, datetime.now(timezone.utc)))))

    def reports(self) -> tuple[ReconciliationReport, ...]:
        return tuple(CODEC.loads(p) for p in self.repository.evidence(REPORTS))

    def blocked(self) -> bool:
        return bool(self.repository.evidence(FAILURES)) or any(not r.matched for r in self.reports())
