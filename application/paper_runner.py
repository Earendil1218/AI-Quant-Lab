"""Thin offline-first orchestration with explicit authority and conservative gates.

薄应用层：组合既有 domain，不包含 broker 网络循环或自动重试。
"""

from uuid import uuid4

from application.planning import PlanningTicket, StalePlanningDecision
from execution import (
    DispatchOperation, authorize_execution_order, begin_submission, create_execution_order,
    apply_dispatch_result,
)
from execution.recovery import RecoveryAction
from portfolio.planning import plan_target_order
from risk import evaluate_order_risk


class PaperRunner:
    """One serialized application scope; adapters must use this store's durable claims.

    单一串行调用方；仅接收配置好持久化 claim 的 adapter，真实 transport 仍锁闭。
    """

    def __init__(self, repository, adapter):
        # Explicit composition check prevents accidentally wiring the 3H memory claim.
        # 显式检查组合，避免误用会在重启丢失的 3H 内存 claim。
        from infrastructure.sqlite_execution import SQLiteAttemptClaims
        claims = getattr(adapter, "claims", None)
        if not isinstance(claims, SQLiteAttemptClaims) or claims.repository.path != repository.path:
            raise ValueError("runner requires the same database's persistent adapter claims")
        self.repository = repository
        self.adapter = adapter
        self._observation_session = None

    def _ready(self, *, dispatch_id=None):
        if self._observation_session is not None:
            from broker.ibkr.session import SessionState
            if self._observation_session.state is not SessionState.READY:
                raise ValueError("observation session is not ready")
        from infrastructure.reconciliation import ReconciliationStore
        if ReconciliationStore(self.repository).blocked():
            raise ValueError("durable reconciliation evidence requires review")
        if (self.repository.unresolved_observations() or self.repository.pending_accounting_count()
                or self.repository.pending_inbox_count()):
            raise ValueError("unresolved evidence/accounting requires recovery review")
        for candidate in self.repository.list_recovery_candidates():
            if (candidate.order.client_order_id != dispatch_id
                    or candidate.action is not RecoveryAction.ATTEMPT_ALLOWED):
                raise ValueError("outstanding execution requires recovery/reconciliation")

    def plan(self, intent, sizing, configuration, valuation):
        """Delegate planning/risk using reconstructed accounting. / 重建组合后委托规划与风控。"""
        self._ready()
        portfolio, revision = self.repository.planning_snapshot()
        plan = plan_target_order(intent, sizing, portfolio)
        decision = None if plan.request is None else evaluate_order_risk(
            plan.request, portfolio, valuation, configuration)
        ticket = PlanningTicket(str(uuid4()), revision, plan, decision)
        self.repository.register_planning(ticket.planning_id, revision, plan, decision)
        return ticket

    def prepare(self, ticket: PlanningTicket, authorization, *, prepared_at):
        """Persist an explicitly authorized pending order; never manufacture approval.

        消费调用方显式授权，先验证纯转换，再保存状态；不自动创建审批。
        """
        self._ready()
        if not isinstance(ticket, PlanningTicket) or ticket.plan.request is None:
            raise StalePlanningDecision("a fresh actionable PlanningTicket is required")
        request, risk_decision = ticket.plan.request, ticket.risk_decision
        order = create_execution_order(request, request.created_at, authorization.client_order_id)
        authorized = authorize_execution_order(order, risk_decision, authorization)
        pending = begin_submission(authorized, prepared_at)
        self.repository.add_planned(order, ticket.planning_id, ticket.portfolio_revision, ticket.plan, risk_decision)
        self.repository.save(authorized, order.version)
        self.repository.save(pending, authorized.version)
        return pending

    def dispatch(self, client_order_id, *, applied_at):
        """At most one attempt; restart uncertainty requires observations, never resend.

        仅首次提交；claim 由 adapter 在准备后消费，任何异常都不释放。
        """
        self._ready(dispatch_id=client_order_id)
        order = self.repository.get(client_order_id)
        if order is None:
            raise KeyError("unknown execution")
        if applied_at < order.updated_at:
            raise ValueError("dispatch time precedes pending state")
        self.repository.validate_planned(client_order_id)
        result = self.adapter.submit(order)
        if result.operation is not DispatchOperation.SUBMIT:
            raise ValueError("unexpected dispatch operation")
        updated = apply_dispatch_result(order, result, applied_at)
        if updated != order:
            self.repository.save(updated, order.version)
        return result

    def consume(self, observation, *, applied_at):
        """Lifecycle/fill commit precedes a separately recoverable accounting step.

        成交提交先于记账；后续调用 account_pending，即使中间崩溃也不丢失。
        """
        order = self.repository.get(observation.client_order_id)
        if order is None:
            raise KeyError("unknown execution")
        return self.repository.apply_observation(observation, applied_at=applied_at, expected_version=order.version)

    def recover(self):
        """Return work requiring attention; no dispatch or state reset.

        返回恢复清单和未决证据，不执行发送、重试或清除 claim。
        """
        return (self.repository.list_recovery_candidates(),
                self.repository.unresolved_observations(), self.repository.pending_accounting_count(),
                self.repository.pending_inbox_count())

    def consume_inbox(self, inbox, *, applied_at):
        """Replay a fixed batch; acknowledge only after every observation commits.

        任意中断保留待处理标记，重启重放由持久化成交身份去重。
        """
        if inbox.repository.path != self.repository.path:
            raise ValueError("inbox belongs to another execution scope")
        through_seq, observations, unpaired = inbox.replay_batch()
        for observation in observations:
            self.consume(observation, applied_at=applied_at)
        if not unpaired:
            self.repository.mark_inbox_consumed(inbox.namespace, through_seq)

    def account_pending(self):
        return self.repository.account_pending()

    def reconcile_session(self, session, *, integration_opt_in: bool = False):
        """Explicit connect/query/reconcile; never dispatch or repair local facts.

        启动/重连核对仅编排；失败持久化并降级，绝不自动重发或清除 UNKNOWN。
        """
        from broker.ibkr.observation import owned_identities
        from infrastructure.reconciliation import ReconciliationStore

        store = ReconciliationStore(self.repository)
        self._observation_session = session
        try:
            session.connect(integration_opt_in=integration_opt_in)
            snapshot = session.observe()
            report = store.reconcile(snapshot, owned_identities)
            blocked = (store.blocked() or bool(self.repository.unresolved_observations())
                       or self.repository.pending_accounting_count() > 0
                       or self.repository.pending_inbox_count() > 0)
            session.reconciled(report, blocked=blocked)
            return report
        except Exception:
            session.degrade()
            store.failure(session.generation, "SESSION_OR_RECONCILIATION_FAILED")
            raise
