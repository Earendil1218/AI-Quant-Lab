# Phase 3J — IBKR Paper Execution & Reconciliation Foundation

中文：基线为 Phase 3I merge `574d1a55aa7b1790cb24a0727da0ea0c58653736`，本阶段未提交。版本保留 v0.10，不建立新发布策略。真实 place/cancel 始终锁闭，未进行在线验收。

English: This is a read-only observation and recovery foundation, not an autonomous live or Paper trading system. Real submission and cancellation remain unconditionally locked. No automatic retry, resend, cancellation, position repair or approval is introduced.

## Data flow / 数据流

```text
Strategy Intent -> Target/Sizing Plan -> Pre-Trade Risk -> PlanningTicket
 -> Explicit Authorization -> Durable Execution -> Durable Claim
 -> IBKR Paper Adapter (real place/cancel LOCKED)

Explicit read-only session -> bounded broker queries -> raw callbacks
 -> IBKR mapper -> broker-neutral snapshot -> pure reconciliation
 -> durable reconciliation evidence -> readiness decision
```

Broker observation is not authority to mutate arbitrary local state. Reconciliation writes evidence beside durable execution state; it does not overwrite the aggregate, manufacture a Fill, consume/release claims or change accounting. Existing fee-complete execution/commission ingestion remains a separate explicit path.

## Modules / 模块

| Module | Responsibility |
|---|---|
| `execution.broker_state` | Immutable neutral order/execution/account-scope snapshots, ownership projections, pure matching and results |
| `broker.ibkr.observation` | Existing raw callback types to neutral facts; persisted broker mappings to neutral ownership |
| `broker.ibkr.session` | DISCONNECTED → CONNECTING → CONNECTED → READY or DEGRADED, explicit connection/query only |
| `broker.ibkr.transport` | Existing locked transport plus bounded `reqAllOpenOrders` / account-filtered `reqExecutions` query seam |
| `infrastructure.reconciliation` | Atomic report/query persistence using existing schema-v2 evidence table |
| `application.paper_runner` | `reconcile_session` orchestration and persistent/session readiness gates |

## Session and query boundaries / 会话与查询边界

CONNECTED means validated API connectivity, not readiness. READY means the current query was complete, its observations matched and no durable reconciliation/callback/accounting blocker remained. READY never unlocks transport, clears UNKNOWN, or grants approval. Outstanding executions still block planning through the existing runner gate. A disconnected READY session degrades; another attempt requires a fresh session/generation and explicit orchestration, never automatic reconnect.

Configuration must explicitly select PAPER, the supported local endpoint and exactly one independently verified allowlisted account. Current managed accounts must match exactly before and after querying. Ports and account prefixes do not prove Paper status. A misconfigured allowlist cannot be cryptographically verified as Paper by this API; connectivity may reach an endpoint before managed-account validation rejects it. Real sends remain impossible regardless of configuration. No online call was made for this implementation.

Queries have a 10-second request timeout and are one-shot per transport. They use raw wrapper events, not synthesized mutable Trade status. Raw events remain available in the queue. Error/disconnect events invalidate completeness; orphan status events also prevent an empty snapshot from proving absence. Conflicting duplicate callbacks fail closed. Query completion describes the requested broker-visible window, not unlimited execution history or an atomic exchange snapshot. `reqAllOpenOrders` does not maintain other clients' orders in sync. Subsequent broker changes require a fresh explicit query.

Open-order quantity/status mapping uses raw `openOrder` and compatible `orderStatus`. If the broker query supplies no quantity status, quantities remain unknown: no default zero is invented and readiness is blocked. Supported observations are STK/USD, integer quantities and MKT BUY/SELL; execution BOT/SLD maps explicitly to neutral sides. Invalid contract, number, timestamp, side or account fails. Unknown status maps to UNKNOWN with a diagnostic. Account observation is only validated account identity/managed-account scope, not balances or positions.

## Matching / 核对规则

| Status | Meaning and action |
|---|---|
| MATCHED | Unique durable strong identity and compatible facts; evidence only, no lifecycle repair |
| BROKER_ONLY | No reliable durable owner; retain evidence, never adopt |
| LOCAL_ONLY | Complete query lacks an outstanding local order; never infer rejection or resend |
| CONFLICT | Ambiguous identity, contradictory ownership, contract/request/economics or terminal-local/open-broker mismatch; stop |
| UNKNOWN | Incomplete/stale evidence, missing quantity/fee-complete execution, or state requiring explicit review; stop |

Stable account/permId matches across generations. API client/order IDs match only within the original generation. Symbol/side/quantity do not establish ownership. A new-session observation cannot acquire an old order solely by reusing its API ID or orderRef. When a crash precedes durable permId evidence, a later cross-generation match may remain BROKER_ONLY/LOCAL_ONLY rather than guessing. A durable permId can recover MATCHED even if the lifecycle acknowledgement was not committed.

Execution observations compare exact execution identity, quantity, price and execution time with accepted local fills. New executions or revisions require the existing fee-complete ingestion/review path; reconciliation never adds economic effects. An execution does not prove that an outstanding order is currently open. Cancellation intent and completion require explicit review rather than automatic transitions.

## Persistence / 持久化

The existing SQLite v2 `evidence` table stores versioned reconciliation query envelopes, reports and failure diagnostics; no database version bump or historical migration is required. Reports include the snapshot, local order versions, local/broker identities, result codes and observation timestamp. Hash identity is deterministic. Exact query replay is idempotent; reuse of a query ID with different facts is rejected. Repeated callbacks collapse within a query. Semantically identical facts across a new query/reconnect retain one report when stable permanent identity exists; separate immutable query envelopes retain session/time provenance. Facts without permanent identity retain generation scope.

Local aggregates and identity mappings are read consistently and rechecked in the report commit transaction. Concurrent changes reject the stale report with no partial persistence. Reports and query binding commit together. Crash before commit leaves no partial report; crash after commit permits replay. No reconciliation operation touches fill/accounting tables.

Non-MATCHED reports and query/session failure diagnostics remain durable blockers, including after restart and later MATCHED queries. This phase deliberately has no blanket clearing or automatic repair API. Failure records use a stable diagnostic code and timestamp, not arbitrary exception strings that might expose account data. Database contents themselves contain account-scoped audit evidence and belong in controlled runtime storage, never Git.

## Validation and deferred work / 验证与后续

Offline tests use real SQLite stores, fake sessions and the existing network/order prohibition fixture. They cover A–F recovery scenarios, mapping, ambiguity, incomplete queries, genuine UNKNOWN retention, round trips, duplicate facts across reconnect, stale local writes, query failures and the real read-only query seam with an injected IB stub. Full-suite, compile/import and diff validation are reported in the development report. No external credentials or operational database are required.

Deferred to separately authorized work: verified online/manual connectivity acceptance, broker history gap recovery, completed-order queries, explicit uncertainty resolution/repair, safe cross-session recovery when permanent identity is absent, fee-complete cross-session ingestion, approval workflow, schema migration tooling, real order unlocking, continuous reconciliation, multi-process coordination, monitoring and HA. No Phase 4 capability is added.

Local validation: 591 passed / 0 failed / 1 skipped (54 new cases); compile 104 Python files and import 69 production modules. The only skip remains the existing opt-in readonly online test. No lint/type-check configuration is present in the repository.
