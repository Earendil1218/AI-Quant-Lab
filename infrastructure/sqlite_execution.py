"""Single-process SQLite execution storage. / 单进程 SQLite 执行持久化。

One file owns one execution/accounting scope. Callers serialize application
dispatch and state writes; SQL transactions protect repository/claim races.
一个数据库对应一个账户作用域；不提供多进程调度或 broker 原子提交。
"""

from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from hashlib import sha256
import sqlite3

from execution.adapter import DispatchOperation
from execution.dispatch import AttemptClaim, StaleIntentError
from execution.models import ClientOrderId, ExecutionOrder, ExecutionOrderState as State, TERMINAL_EXECUTION_STATES
from execution.observations import ExecutionObservation, ObservationApplication, ObservationKind, apply_execution_observation
from execution.recovery import RecoveryCandidate, StalePlanningDecision, classify_recovery
from infrastructure.accounting import ACCOUNTING_POLICY, accounting_context
from infrastructure.codec import Codec
from portfolio.state import PortfolioState


class VersionConflict(ValueError):
    """A stale writer cannot overwrite durable state. / 拒绝过期写入。"""


class SQLiteExecutionRepository:
    """Existing add/get/save contract plus explicit recovery/accounting operations.

    保持已有 repository API；独立连接、显式事务、无隐式时间和网络访问。
    """

    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        self.codec = Codec()
        with self._transaction() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 2):
                raise ValueError("unsupported execution database version")
            for statement in (
                "CREATE TABLE IF NOT EXISTS executions (id TEXT PRIMARY KEY, version INTEGER NOT NULL, payload TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS claims (id TEXT NOT NULL REFERENCES executions(id), operation TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(id,operation))",
                "CREATE TABLE IF NOT EXISTS fills (seq INTEGER PRIMARY KEY, fill_id TEXT UNIQUE NOT NULL, broker_id TEXT UNIQUE, order_id TEXT NOT NULL REFERENCES executions(id), payload TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS accounting (fill_id TEXT PRIMARY KEY REFERENCES fills(fill_id))",
                "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS observations (seq INTEGER PRIMARY KEY, order_id TEXT NOT NULL REFERENCES executions(id), payload TEXT NOT NULL, unresolved INTEGER NOT NULL, reason TEXT NOT NULL DEFAULT '', correlation_key TEXT, resolved_at TEXT, resolved_by TEXT)",
                "CREATE TABLE IF NOT EXISTS evidence (namespace TEXT NOT NULL, key TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(namespace,key))",
                "CREATE TABLE IF NOT EXISTS inbox (seq INTEGER PRIMARY KEY, namespace TEXT NOT NULL, payload TEXT NOT NULL, consumed INTEGER NOT NULL DEFAULT 0)",
                "CREATE TABLE IF NOT EXISTS planning (id TEXT PRIMARY KEY, revision TEXT NOT NULL, payload TEXT NOT NULL, order_id TEXT UNIQUE REFERENCES executions(id))",
                "CREATE TABLE IF NOT EXISTS scoped_ownership (kind TEXT NOT NULL, scope TEXT NOT NULL, identity TEXT NOT NULL, order_id TEXT NOT NULL REFERENCES executions(id), PRIMARY KEY(kind,scope,identity), UNIQUE(kind,scope,order_id))",
                "CREATE TABLE IF NOT EXISTS permanent_ownership (kind TEXT NOT NULL, scope TEXT NOT NULL, identity TEXT NOT NULL, order_id TEXT NOT NULL REFERENCES executions(id), PRIMARY KEY(kind,scope,identity), UNIQUE(kind,order_id))",
                "CREATE TABLE IF NOT EXISTS execution_families (namespace TEXT NOT NULL, family TEXT NOT NULL, execution_id TEXT NOT NULL, order_id TEXT NOT NULL REFERENCES executions(id), PRIMARY KEY(namespace,family), UNIQUE(namespace,execution_id))",
            ):
                db.execute(statement)
            db.execute("PRAGMA user_version=2")

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _get(self, db, cid):
        if not isinstance(cid, ClientOrderId):
            raise TypeError("client_order_id must be a ClientOrderId")
        row = db.execute("SELECT payload FROM executions WHERE id=?", (cid.value,)).fetchone()
        return None if row is None else self.codec.loads(row[0])

    def get(self, client_order_id: ClientOrderId) -> ExecutionOrder | None:
        """Load an immutable aggregate or None. / 读取不可变执行快照。"""
        with self._transaction() as db:
            return self._get(db, client_order_id)

    def _persist_fills(self, db, order):
        if sum(f.fill.quantity for f in order.fills) != order.cumulative_filled_quantity:
            raise ValueError("economic quantity requires complete fill evidence")
        for fill in order.fills:
            payload = self.codec.dumps(fill)
            bid = None if fill.broker_execution_id is None else fill.broker_execution_id.value
            rows = db.execute("SELECT payload FROM fills WHERE fill_id=? OR broker_id=?",
                              (fill.fill_id.value, bid)).fetchall()
            if rows:
                if any(row[0] != payload for row in rows):
                    raise ValueError("durable fill identity conflict")
            else:
                db.execute("INSERT INTO fills(fill_id,broker_id,order_id,payload) VALUES(?,?,?,?)",
                           (fill.fill_id.value, bid, order.client_order_id.value, payload))

    def add(self, order: ExecutionOrder) -> None:
        """Insert once, including any economic identities. / 唯一插入并保存经济身份。"""
        if not isinstance(order, ExecutionOrder):
            raise TypeError("order must be an ExecutionOrder")
        with self._transaction() as db:
            if self._get(db, order.client_order_id) is not None:
                raise ValueError("ClientOrderId already exists")
            db.execute("INSERT INTO executions VALUES(?,?,?)",
                       (order.client_order_id.value, order.version, self.codec.dumps(order)))
            self._persist_fills(db, order)

    def _save(self, db, order, expected_version, *, record_uncertainty=True):
        if not isinstance(order, ExecutionOrder) or type(expected_version) is not int:
            raise TypeError("typed order and integer expected_version required")
        current = self._get(db, order.client_order_id)
        if current is None:
            raise KeyError("execution order does not exist")
        if current.version != expected_version:
            raise VersionConflict("stale execution order version")
        if order.version != expected_version + 1:
            raise ValueError("saved order must advance version by exactly one")
        if (order.request != current.request or order.created_at != current.created_at
                or order.updated_at < current.updated_at
                or (current.authorization is not None and current.authorization != order.authorization)
                or (current.broker_order_id is not None and current.broker_order_id != order.broker_order_id)
                or order.fills[:len(current.fills)] != current.fills):
            raise ValueError("immutable execution facts cannot be replaced")
        changed = db.execute("UPDATE executions SET version=?,payload=? WHERE id=? AND version=?",
                             (order.version, self.codec.dumps(order), order.client_order_id.value, expected_version))
        if changed.rowcount != 1:
            raise VersionConflict("stale execution order version")
        # 同一事务保存 aggregate 与去重身份。 / Aggregate and dedup commit together.
        self._persist_fills(db, order)
        if record_uncertainty and order.state is State.UNKNOWN:
            observation = ExecutionObservation(order.client_order_id, order.request,
                ObservationKind.UNRESOLVED, order.updated_at, order.broker_order_id,
                detail="UNKNOWN requires explicit reconciliation; fills cannot clear delivery uncertainty")
            db.execute("INSERT INTO observations(order_id,payload,unresolved,reason) VALUES(?,?,1,'UNKNOWN')",
                       (order.client_order_id.value, self.codec.dumps(observation)))

    def save(self, order: ExecutionOrder, expected_version: int) -> None:
        """Compare-and-swap state and fills atomically. / 原子校验版本并保存状态与成交。"""
        with self._transaction() as db:
            self._save(db, order, expected_version)

    def list_recovery_candidates(self) -> tuple[RecoveryCandidate, ...]:
        """Read nonterminal state without resetting claims. / 不清除 claim 的恢复清单。"""
        with self._transaction() as db:
            results = []
            for row in db.execute("SELECT payload FROM executions ORDER BY id"):
                order = self.codec.loads(row[0])
                if order.state not in TERMINAL_EXECUTION_STATES:
                    operations = tuple(r[0] for r in db.execute(
                        "SELECT operation FROM claims WHERE id=? ORDER BY operation", (order.client_order_id.value,)))
                    results.append(classify_recovery(order, operations))
            return tuple(results)

    def apply_observation(self, observation: ExecutionObservation, *, applied_at: datetime,
                          expected_version: int) -> ObservationApplication:
        """Validate, apply, save fills and retain unresolved evidence atomically.

        观察、状态、成交去重同一事务；异常整体回滚，不自动清除历史未决证据。
        """
        with self._transaction() as db:
            order = self._get(db, observation.client_order_id)
            if order is None:
                raise KeyError("unknown execution")
            if type(expected_version) is not int or order.version != expected_version:
                raise VersionConflict("stale observation version")
            payload = self.codec.dumps(observation)
            if applied_at < order.updated_at or applied_at < observation.observed_at:
                raise ValueError("application time precedes state or observation")
            # 已提交的原始观察不再次推动状态；迟到成交仍走经济身份校验。
            # Replayed committed facts cannot undo newer uncertainty or cancellation.
            if db.execute("SELECT 1 FROM observations WHERE order_id=? AND payload=?",
                          (order.client_order_id.value, payload)).fetchone():
                return ObservationApplication(order)
            if observation.kind is not ObservationKind.FILL and observation.observed_at < order.updated_at:
                # Validate bindings even when an old snapshot cannot advance lifecycle.
                # 旧快照也必须验证身份，不能把冲突静默当成 stale。
                if (observation.request != order.request
                        or (order.broker_order_id is not None and observation.broker_order_id is not None
                            and order.broker_order_id != observation.broker_order_id)):
                    raise ValueError("stale observation identity/request conflict")
                result = ObservationApplication(order, unresolved=True)
            else:
                result = apply_execution_observation(order, observation, applied_at=applied_at)
            if result.order != order:
                self._save(db, result.order, expected_version, record_uncertainty=False)
            correlation = (None if observation.pending_execution_id is None
                           else observation.pending_execution_id.value)
            reason = "WAITING_FOR_COMMISSION" if correlation is not None else observation.kind.value
            db.execute("INSERT INTO observations(order_id,payload,unresolved,reason,correlation_key) VALUES(?,?,?,?,?)",
                       (order.client_order_id.value, payload, int(result.unresolved), reason, correlation))
            # Only matching, durably accepted economics resolve a pairing wait.
            # 仅匹配的已持久化经济成交可以解决等待佣金；不清除任何真正未知状态。
            for fill in result.order.fills:
                if fill.broker_execution_id is not None:
                    db.execute("UPDATE observations SET resolved_at=?,resolved_by=? "
                               "WHERE order_id=? AND reason='WAITING_FOR_COMMISSION' AND correlation_key=? "
                               "AND unresolved=1 AND resolved_at IS NULL",
                               (applied_at.isoformat(), fill.fill_id.value, order.client_order_id.value,
                                fill.broker_execution_id.value))
            return result

    def unresolved_observations(self) -> tuple[ExecutionObservation, ...]:
        """Return active blockers, retaining resolved waits in the audit table.

        返回尚未解决的观察；仅匹配成交解决配对等待，普通 ack 不清除未知状态。
        """
        with self._transaction() as db:
            return tuple(self.codec.loads(r[0]) for r in db.execute(
                "SELECT payload FROM observations WHERE unresolved=1 AND resolved_at IS NULL ORDER BY seq"))

    def initialize_accounting(self, initial_cash: Decimal) -> None:
        """Bind one immutable initial balance; no cash reset on restart.

        一个数据库只对应一个组合；初始现金不可在重启后重置。
        """
        PortfolioState(initial_cash)
        with self._transaction() as db:
            row = db.execute("SELECT value FROM metadata WHERE key='initial_cash'").fetchone()
            if row is not None and Decimal(row[0]) != initial_cash:
                raise ValueError("initial cash already bound")
            db.execute("INSERT OR IGNORE INTO metadata VALUES('initial_cash',?)", (str(initial_cash),))

    def _portfolio(self, db, *, include_pending=False):
        row = db.execute("SELECT value FROM metadata WHERE key='initial_cash'").fetchone()
        if row is None:
            raise ValueError("accounting must be explicitly initialized")
        state = PortfolioState(Decimal(row[0]))
        condition = "" if include_pending else " WHERE fill_id IN (SELECT fill_id FROM accounting)"
        with accounting_context():
            for row in db.execute("SELECT payload FROM fills" + condition + " ORDER BY seq"):
                state.apply_fill(self.codec.loads(row[0]).fill)
        return state

    def _portfolio_revision(self, db):
        cash = db.execute("SELECT value FROM metadata WHERE key='initial_cash'").fetchone()
        if cash is None:
            raise ValueError("accounting must be explicitly initialized")
        facts = (ACCOUNTING_POLICY, cash[0], tuple(row[0] for row in db.execute(
            "SELECT payload FROM fills WHERE fill_id IN (SELECT fill_id FROM accounting) ORDER BY seq")))
        return sha256(self.codec.dumps(facts).encode("utf-8")).hexdigest()

    def planning_snapshot(self):
        """Read accounting and its deterministic revision together. / 同事务读取组合与 revision。"""
        with self._transaction() as db:
            return self._portfolio(db), self._portfolio_revision(db)

    def register_planning(self, planning_id, revision, plan, risk_decision):
        """Persist the complete immutable plan/risk binding. / 保存完整规划与风控绑定。"""
        with self._transaction() as db:
            if self._portfolio_revision(db) != revision:
                raise StalePlanningDecision("portfolio changed during planning")
            db.execute("INSERT INTO planning(id,revision,payload) VALUES(?,?,?)",
                       (planning_id, revision, self.codec.dumps((plan, risk_decision))))

    def add_planned(self, order, planning_id, revision, plan, risk_decision):
        """Consume a fresh planning identity and create execution atomically.

        同事务校验 revision、完整 request/risk、一次性规划身份；不自动重新规划。
        """
        with self._transaction() as db:
            row = db.execute("SELECT revision,payload,order_id FROM planning WHERE id=?", (planning_id,)).fetchone()
            if (row is None or row[2] is not None or row[0] != revision
                    or self._portfolio_revision(db) != revision
                    or row[1] != self.codec.dumps((plan, risk_decision))
                    or plan.request != order.request or risk_decision is None
                    or risk_decision.request != order.request):
                raise StalePlanningDecision("stale, consumed or mismatched planning/risk evidence")
            db.execute("INSERT INTO executions VALUES(?,?,?)",
                       (order.client_order_id.value, order.version, self.codec.dumps(order)))
            self._persist_fills(db, order)
            db.execute("UPDATE planning SET order_id=? WHERE id=?", (order.client_order_id.value, planning_id))

    def _validate_planned(self, db, client_order_id, *, required):
        row = db.execute("SELECT revision FROM planning WHERE order_id=?", (client_order_id.value,)).fetchone()
        if (row is None and required) or (row is not None and row[0] != self._portfolio_revision(db)):
            raise StalePlanningDecision("execution has missing or stale planning evidence")

    def validate_planned(self, client_order_id):
        """Recheck before dispatch; claim repeats the check atomically. / 发送前复核，claim 内再次校验。"""
        with self._transaction() as db:
            self._validate_planned(db, client_order_id, required=True)

    def load_portfolio(self) -> PortfolioState:
        """Reconstruct a fresh view from accounted fills. / 从已记账成交重建独立组合。"""
        with self._transaction() as db:
            return self._portfolio(db)

    def pending_accounting_count(self) -> int:
        """Count durable economic gaps. / 返回待记账成交数量。"""
        with self._transaction() as db:
            return db.execute("SELECT COUNT(*) FROM fills WHERE fill_id NOT IN (SELECT fill_id FROM accounting)").fetchone()[0]

    def account_pending(self) -> PortfolioState:
        """Validate all pending economics then atomically mark them accounted.

        不修改外部 PortfolioState；重建结果与记账标记同一事务，重放不会重复扣款。
        """
        with self._transaction() as db:
            state = self._portfolio(db, include_pending=True)
            db.execute("INSERT OR IGNORE INTO accounting SELECT fill_id FROM fills")
            return state

    def put_evidence(self, namespace, key, payload, *, expected_payload=None,
                     scoped_identities=(), permanent_identities=()):
        """Opaque adapter evidence with compare-and-swap replacement.

        broker 类型由 adapter 编解码，基础设施不导入 broker。
        """
        with self._transaction() as db:
            row = db.execute("SELECT payload FROM evidence WHERE namespace=? AND key=?", (namespace, key)).fetchone()
            current = None if row is None else row[0]
            if current != payload and current != expected_payload:
                raise VersionConflict("stale adapter evidence")
            for table, identities in (("scoped_ownership", scoped_identities),
                                      ("permanent_ownership", permanent_identities)):
                for kind, scope, identity in identities:
                    try:
                        db.execute(f"INSERT INTO {table} VALUES(?,?,?,?) "
                                   "ON CONFLICT(kind,scope,identity) DO NOTHING", (kind, scope, identity, key))
                    except sqlite3.IntegrityError as exc:
                        raise ValueError("conflicting durable broker identity") from exc
                    owner = db.execute(f"SELECT order_id FROM {table} WHERE kind=? AND scope=? AND identity=?",
                                       (kind, scope, identity)).fetchone()
                    if owner is None or owner[0] != key:
                        raise ValueError("broker identity already belongs to another local order")
            db.execute("INSERT INTO evidence VALUES(?,?,?) ON CONFLICT(namespace,key) DO UPDATE SET payload=excluded.payload",
                       (namespace, key, payload))

    def claim_execution_family(self, namespace, family, execution_id, client_order_id):
        """Retain correction-family ownership across sessions; never book revisions.

        跨会话保留 correction family；不同完整 execution ID 必须核对，不能当新成交。
        """
        with self._transaction() as db:
            db.execute("INSERT INTO execution_families VALUES(?,?,?,?) "
                       "ON CONFLICT(namespace,family) DO NOTHING",
                       (namespace, family, execution_id, client_order_id.value))
            row = db.execute("SELECT execution_id,order_id FROM execution_families WHERE namespace=? AND family=?",
                             (namespace, family)).fetchone()
            if row != (execution_id, client_order_id.value):
                raise ValueError("CORRECTION_REQUIRES_RECONCILIATION: durable execution family conflict")

    def evidence(self, namespace):
        with self._transaction() as db:
            return tuple(r[0] for r in db.execute("SELECT payload FROM evidence WHERE namespace=? ORDER BY key", (namespace,)))

    def append_inbox(self, namespace, payload):
        """Commit raw input before normalization. / 归一化之前保存原始输入。"""
        with self._transaction() as db:
            db.execute("INSERT INTO inbox(namespace,payload) VALUES(?,?)", (namespace, payload))

    def inbox(self, namespace):
        return tuple(payload for _, payload in self.inbox_entries(namespace))

    def inbox_entries(self, namespace):
        with self._transaction() as db:
            return tuple(db.execute("SELECT seq,payload FROM inbox WHERE namespace=? ORDER BY seq", (namespace,)))

    def mark_inbox_consumed(self, namespace, through_seq):
        """Only after neutral observations commit. / 中立观察提交后才能标记已消费。"""
        with self._transaction() as db:
            db.execute("UPDATE inbox SET consumed=1 WHERE namespace=? AND seq<=?", (namespace, through_seq))

    def pending_inbox_count(self) -> int:
        """Count raw records not fully consumed. / 返回尚未完整消费的回调数量。"""
        with self._transaction() as db:
            return db.execute("SELECT COUNT(*) FROM inbox WHERE consumed=0").fetchone()[0]


class SQLiteAttemptClaims:
    """Restart-safe one-shot claim with no release/reset API.

    永久消费 logical operation；SQL 唯一键及事务保护并发，崩溃不释放。
    """

    def __init__(self, repository: SQLiteExecutionRepository):
        self.repository = repository

    def _validate(self, db, order, operation, *, consumed=False):
        if not isinstance(order, ExecutionOrder) or not isinstance(operation, DispatchOperation):
            raise TypeError("typed order and operation required")
        required = State.SUBMISSION_PENDING if operation is DispatchOperation.SUBMIT else State.CANCEL_PENDING
        if order.state is not required or order.authorization is None:
            raise ValueError("claim requires authorized pending intent")
        if operation is DispatchOperation.CANCEL and order.broker_order_id is None:
            raise ValueError("cancellation requires broker identity")
        if self.repository._get(db, order.client_order_id) != order:
            raise StaleIntentError("pending intent is not the current saved order")
        self.repository._validate_planned(db, order.client_order_id, required=False)
        row = db.execute("SELECT payload FROM claims WHERE id=? AND operation=?",
                         (order.client_order_id.value, operation.value)).fetchone()
        if consumed:
            if row is None or self.repository.codec.loads(row[0]) != order:
                raise ValueError("no matching consumed claim")
        elif row is not None:
            raise ValueError("operation already claimed; automatic retry forbidden")

    def validate(self, order: ExecutionOrder, operation: DispatchOperation) -> None:
        """Validate without consuming authority. / 验证但不消费授权。"""
        with self.repository._transaction() as db:
            self._validate(db, order, operation)

    def claim(self, order: ExecutionOrder, operation: DispatchOperation) -> AttemptClaim:
        """Commit one logical attempt before returning. / 返回之前提交一次性 claim。"""
        with self.repository._transaction() as db:
            self._validate(db, order, operation)
            db.execute("INSERT INTO claims VALUES(?,?,?)",
                       (order.client_order_id.value, operation.value, self.repository.codec.dumps(order)))
        return AttemptClaim(order, operation)

    def verify_current(self, order: ExecutionOrder, operation: DispatchOperation) -> None:
        """Verify consumed snapshot without renewal. / 校验已消费快照，绝不续期。"""
        with self.repository._transaction() as db:
            self._validate(db, order, operation, consumed=True)
