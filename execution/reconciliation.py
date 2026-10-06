"""Conservative snapshot comparison without I/O or automatic state changes.

保守快照核对；不执行 I/O、不伪造成交、不自动重发。
"""

from dataclasses import dataclass
from enum import Enum

from execution.models import BrokerOrderObservation, ExecutionOrder, ExecutionOrderState as State


class ReconciliationDecision(str, Enum):
    CONSISTENT = "consistent"
    ACKNOWLEDGEMENT_AVAILABLE = "acknowledgement_available"
    ECONOMIC_EVIDENCE_REQUIRED = "economic_evidence_required"
    STALE = "stale"
    MISSING = "missing"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class ReconciliationAssessment:
    decision: ReconciliationDecision
    detail: str


def assess_reconciliation(order: ExecutionOrder, observation: BrokerOrderObservation | None) -> ReconciliationAssessment:
    """Reuse the existing broker-neutral snapshot; quantities are evidence only.

    使用现有 observation；缺失和 UNKNOWN 均不提供 retry 权限。
    """
    def result(decision, detail):
        return ReconciliationAssessment(decision, detail)
    D = ReconciliationDecision
    if observation is None:
        return result(D.MISSING, "No broker evidence; no resend permission.")
    if (observation.client_order_id != order.client_order_id
            or (order.broker_order_id is not None and observation.broker_order_id != order.broker_order_id)):
        return result(D.CONFLICT, "Broker/local identity conflict.")
    if observation.cumulative_filled_quantity > order.request.quantity:
        return result(D.CONFLICT, "Broker quantity exceeds request.")
    if observation.observed_at < order.updated_at:
        return result(D.STALE, "Observation predates local state; retain local facts.")
    if observation.state is State.UNKNOWN or observation.broker_order_id is None:
        return result(D.UNKNOWN, "Broker state or identity unresolved.")
    if ((observation.state is State.FILLED and observation.cumulative_filled_quantity != order.request.quantity)
            or (observation.state is State.PARTIALLY_FILLED
                and not 0 < observation.cumulative_filled_quantity < order.request.quantity)):
        return result(D.CONFLICT, "Broker state contradicts its quantity.")
    if observation.cumulative_filled_quantity < order.cumulative_filled_quantity:
        return result(D.CONFLICT, "Broker quantity regresses known economics.")
    if (observation.cumulative_filled_quantity > order.cumulative_filled_quantity
            or (observation.state is State.FILLED and order.remaining_quantity)):
        return result(D.ECONOMIC_EVIDENCE_REQUIRED, "Require executions and actual commissions; never book a snapshot.")
    if order.state is observation.state:
        return result(D.CONSISTENT, "Identity, state and economic quantity agree.")
    if (order.state in {State.SUBMISSION_PENDING, State.SUBMITTED, State.UNKNOWN}
            and observation.state is State.ACKNOWLEDGED and not order.cumulative_filled_quantity):
        return result(D.ACKNOWLEDGEMENT_AVAILABLE, "Apply explicit validated acknowledgement separately.")
    return result(D.CONFLICT, "State mismatch requires explicit review.")
