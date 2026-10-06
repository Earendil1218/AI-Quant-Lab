"""Manual opt-in acceptance harness; never invoked by pytest or application startup.

This function requires caller-created authorization and current-session Paper
confirmation. Environment flags are gates, not human or submission authority.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import os
from time import monotonic

from broker.ibkr.config import PaperSafetyError
from broker.ibkr.paper_transport import PaperExecutionTransport, PaperSessionConfirmation
from execution import DispatchOutcome, ExecutionObservation, ObservationKind, SubmissionAuthorization
from execution.models import ExecutionOrder, ExecutionOrderState, TERMINAL_EXECUTION_STATES
from execution.adapter import DispatchResult
from execution.broker_state import ReconciliationReport


@dataclass(frozen=True)
class PaperIntegrationResult:
    dispatch: DispatchResult
    order: ExecutionOrder
    reconciliation: ReconciliationReport | None


def run_authorized_paper_loop(runner, *, confirmation: PaperSessionConfirmation,
                              intent, sizing, risk_configuration, valuation,
                              authorization: SubmissionAuthorization,
                              integration_opt_in: bool = False,
                              side_effect_opt_in: bool = False,
                              wait_seconds: float = 30.0) -> PaperIntegrationResult:
    """One caller-authorized order, bounded callback wait, accounting and fresh query.

    No authorization is fabricated; no resubmission, automatic reconnect or cancel.
    The caller must verify TWS Simulated/Paper login and manually disable Read-Only
    API only for this acceptance run. This function never edits TWS settings.
    """
    if (integration_opt_in is not True or side_effect_opt_in is not True
            or os.getenv('RUN_IBKR_PAPER_INTEGRATION') != '1'
            or os.getenv('ALLOW_IBKR_PAPER_ORDER_SIDE_EFFECTS') != 'YES'):
        raise PaperSafetyError('manual integration and Paper side-effect gates are both required')
    if type(authorization) is not SubmissionAuthorization or type(confirmation) is not PaperSessionConfirmation:
        raise PaperSafetyError('caller-created human authorization and Paper confirmation required')
    if isinstance(wait_seconds, bool) or not isinstance(wait_seconds, (int, float)) or not math.isfinite(wait_seconds) or not 0 < wait_seconds <= 60:
        raise ValueError('bounded acceptance wait must be between 0 and 60 seconds')
    transport = runner.adapter.transport
    if not isinstance(transport, PaperExecutionTransport):
        raise PaperSafetyError('explicit Paper execution transport required')
    try:
        runner.start_paper_session(confirmation, integration_opt_in=True, side_effect_opt_in=True)
        runner.ingest_callbacks(applied_at=datetime.now(timezone.utc))
        ticket = runner.plan(intent, sizing, risk_configuration, valuation)
        pending = runner.prepare(ticket, authorization, prepared_at=datetime.now(timezone.utc))
        result = runner.dispatch(pending.client_order_id, applied_at=datetime.now(timezone.utc))
        if result.outcome is not DispatchOutcome.DISPATCH_RETURNED:
            return PaperIntegrationResult(result, runner.repository.get(pending.client_order_id), None)
        deadline = monotonic() + wait_seconds
        while True:
            runner.ingest_callbacks(applied_at=datetime.now(timezone.utc))
            runner.account_pending()
            order = runner.repository.get(pending.client_order_id)
            if order.state is ExecutionOrderState.UNKNOWN:
                return PaperIntegrationResult(result, order, None)
            if order.state in TERMINAL_EXECUTION_STATES and not runner.repository.pending_inbox_count():
                break
            if monotonic() >= deadline:
                # A bounded wait expiring cannot prove no delivery. Retain facts
                # and require review; the claim remains permanently consumed.
                now = datetime.now(timezone.utc)
                runner.consume(ExecutionObservation(order.client_order_id, order.request,
                    ObservationKind.CONNECTION_LOST, now, detail='manual acceptance deadline; review required'),
                    applied_at=now)
                return PaperIntegrationResult(result, runner.repository.get(order.client_order_id), None)
            transport._ib.sleep(min(0.1, max(0.0, deadline - monotonic())))
        report = runner.reconcile_paper()
        runner.ingest_callbacks(applied_at=datetime.now(timezone.utc))
        runner.account_pending()
        return PaperIntegrationResult(result, runner.repository.get(pending.client_order_id), report)
    finally:
        transport.close()
