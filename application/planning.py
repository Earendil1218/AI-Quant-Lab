"""Fresh planning evidence, not submission authority. / 规划新鲜度证据，不是提交授权。"""

from dataclasses import dataclass

from risk import RiskDecision
from trading import OrderPlan
from execution.recovery import StalePlanningDecision


@dataclass(frozen=True)
class PlanningTicket:
    """Bind one plan/risk pair to an immutable portfolio revision.

    绑定唯一规划身份、持仓 revision 和完整 plan/risk；prepare 必须重新校验。
    """

    planning_id: str
    portfolio_revision: str
    plan: OrderPlan
    risk_decision: RiskDecision | None
