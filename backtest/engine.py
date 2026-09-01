"""Single-equity daily backtest orchestration with explicit event timing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import pandas as pd

from backtest.adapters import adapt_latest_strategy_intent
from backtest.execution import ExecutionCosts, simulate_next_open_execution
from backtest.results import BacktestResult
from data.validation import validate_market_data
from portfolio.planning import plan_target_order
from portfolio.sizing import SizingPolicy
from portfolio.state import PortfolioSnapshot, PortfolioState
from risk import (
    RiskConfiguration,
    RiskDecision,
    RiskDecisionStatus,
    ValuationContext,
    evaluate_order_risk,
)
from strategies.base import Strategy
from trading.fills import ExecutionRejection, ExecutionRejectionReason, Fill
from trading.instruments import InstrumentId
from trading.orders import OrderPlan, OrderRequest, PlanningDecision


def _as_datetime(value: object) -> datetime:
    return pd.Timestamp(value).to_pydatetime()


@dataclass(frozen=True)
class BacktestEngine:
    """Run an OPEN-execute, CLOSE-mark/observe/plan daily lifecycle."""

    sizing_policy: SizingPolicy
    execution_costs: ExecutionCosts = ExecutionCosts()
    risk_configuration: RiskConfiguration | None = None

    def __post_init__(self) -> None:
        if self.risk_configuration is not None and not isinstance(
            self.risk_configuration, RiskConfiguration
        ):
            raise TypeError("risk_configuration must be a RiskConfiguration or None.")

    def run(
        self,
        market_data: pd.DataFrame,
        strategy: Strategy,
        instrument: InstrumentId,
        *,
        initial_cash: Decimal,
    ) -> BacktestResult:
        validate_market_data(market_data)
        if not isinstance(strategy, Strategy):
            raise TypeError("strategy must implement Strategy.")
        if not isinstance(instrument, InstrumentId):
            raise TypeError("instrument must be an InstrumentId.")
        portfolio = PortfolioState(initial_cash)
        plans: list[OrderPlan] = []
        orders: list[OrderRequest] = []
        fills: list[Fill] = []
        rejections: list[ExecutionRejection] = []
        risk_decisions: list[RiskDecision] = []
        snapshots: list[PortfolioSnapshot] = []
        pending: OrderRequest | None = None

        for position in range(len(market_data)):
            row = market_data.iloc[position]
            session_time = _as_datetime(row["date"])

            # OPEN: only the prior close's pending order may execute.
            if pending is not None:
                risk_approved = True
                if self.risk_configuration is not None:
                    valuation = ValuationContext(
                        observed_at=session_time,
                        prices={
                            instrument: Decimal(str(row["open"])),
                        },
                    )
                    risk_decision = evaluate_order_risk(
                        pending,
                        portfolio,
                        valuation,
                        self.risk_configuration,
                    )
                    risk_decisions.append(risk_decision)
                    if risk_decision.status is RiskDecisionStatus.REJECTED:
                        risk_approved = False
                if risk_approved:
                    outcome = simulate_next_open_execution(
                        pending,
                        open_price=float(row["open"]),
                        filled_at=session_time,
                        portfolio=portfolio,
                        costs=self.execution_costs,
                    )
                    if isinstance(outcome, Fill):
                        portfolio.apply_fill(outcome)
                        fills.append(outcome)
                    else:
                        rejections.append(outcome)
                pending = None

            # CLOSE: mark first, then expose the completed bar to Strategy.
            close_mark = Decimal(str(row["close"]))
            snapshots.append(
                portfolio.snapshot(session_time, {instrument: close_mark})
            )
            visible_history = market_data.iloc[: position + 1].copy(deep=True)
            strategy_output = strategy.generate_intents(visible_history)
            intent = adapt_latest_strategy_intent(strategy_output, instrument)
            plan = plan_target_order(intent, self.sizing_policy, portfolio)
            plans.append(plan)
            if plan.decision is PlanningDecision.ORDER_REQUIRED:
                assert plan.request is not None
                pending = plan.request
                orders.append(pending)

        if pending is not None:
            rejections.append(
                ExecutionRejection(
                    pending,
                    ExecutionRejectionReason.NO_NEXT_BAR,
                    pending.created_at,
                )
            )

        return BacktestResult(
            plans=tuple(plans),
            orders=tuple(orders),
            fills=tuple(fills),
            rejections=tuple(rejections),
            risk_decisions=tuple(risk_decisions),
            snapshots=tuple(snapshots),
        )
