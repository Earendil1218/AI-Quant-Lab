"""Pure restart classification; never authorizes retry. / 纯恢复分类，绝不授权重发。"""

from dataclasses import dataclass
from enum import Enum

from execution.models import ExecutionOrder, ExecutionOrderState as State, TERMINAL_EXECUTION_STATES


class StalePlanningDecision(ValueError):
    """Planning facts differ from the current durable scope. / 规划事实不再匹配持久状态。"""


class RecoveryAction(str, Enum):
    PREPARE = "prepare"
    ATTEMPT_ALLOWED = "attempt_allowed"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    TERMINAL = "terminal"


@dataclass(frozen=True)
class RecoveryCandidate:
    order: ExecutionOrder
    action: RecoveryAction
    claimed_operations: tuple[str, ...]


def classify_recovery(order: ExecutionOrder, claimed_operations: tuple[str, ...]) -> RecoveryCandidate:
    """Claims survive restart; missing broker evidence never means safe resend.

    pending 且无 claim 才允许首次尝试；已确认订单恢复原状态并等待核对。
    """
    if order.state in TERMINAL_EXECUTION_STATES:
        action = RecoveryAction.TERMINAL
    elif order.state in {State.CREATED, State.AUTHORIZED} and not claimed_operations:
        action = RecoveryAction.PREPARE
    elif order.state is State.SUBMISSION_PENDING and not claimed_operations:
        action = RecoveryAction.ATTEMPT_ALLOWED
    else:
        action = RecoveryAction.RECONCILIATION_REQUIRED
    return RecoveryCandidate(order, action, claimed_operations)
