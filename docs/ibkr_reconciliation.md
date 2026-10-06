# Phase 3J — IBKR Paper Execution & Reconciliation Foundation

中文：基线为 Phase 3I merge `574d1a55aa7b1790cb24a0727da0ea0c58653736`，Phase 3J 已通过 PR #11 合并（`bdf08e8` / `a74e0cd`）。版本保留 v0.10，不建立新发布策略。Phase 3J 的真实 place/cancel 保持锁闭；Phase 3K 受控 BUY 见下文，未进行在线验收。

English: This is a read-only observation and recovery foundation, not an autonomous live or Paper trading system. In Phase 3J, real submission and cancellation remained unconditionally locked; Phase 3K adds a separate controlled BUY boundary. No automatic retry, resend, cancellation, position repair or approval is introduced.

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


## Phase 3K integration / 受控执行扩展

Phase 3J 已通过 PR #11 合并（`bdf08e8` / `a74e0cd`）。Phase 3K 基于该合并基线增加独立默认锁闭的 `PaperExecutionTransport` 与显式 application orchestration；以上 3H–J 的全锁闭描述是历史阶段范围，ReadOnlyIBKRTransport 本身仍然只读。

Online Paper integration is opt-in only. Current-session exact-account human confirmation, two explicit caller opt-ins, persisted planning/risk/SubmissionAuthorization, SQLite claim and durable ownership are all required. Startup/fresh reconciliation uses the existing strong-identity comparison and evidence store; MATCH never clears UNKNOWN or creates a fill/approval. Fee-complete full fills can audit-resolve matching pending/held/completion hints only; identity/quantity conflicts and other uncertainty remain blocked.

真实 BUY/MKT 受控开放；真实 SELL 因本地库存不等于 broker 库存保持锁闭，真实 cancel 也保持锁闭。没有自动重试/重连、Live、自动策略或账户同步；配置与 session evidence 不构成 broker 账户类型证明，仍需独立人工核验。详见 [完整执行链路与人工验收](paper_execution_loop.md)。开发验证全部离线，未调用真实 TWS/Paper order。

## Pre-commit safety audit / 提交前安全审查

发送 scope 已改为内部 `_dispatch_scope`，入口验证尚未消费的 durable claim，避免用已消费 claim 重入并绕过 adapter；公开 `place/next_order_id` 没有内部 scope 时仍拒绝。边界使用确切 OrderSide.BUY，并重新核对获授权 instrument 与 spec。连接期 disconnect、connectivity/recovery notice 或未知诊断永久退役该 generation，连接返回不得恢复权限。

未知 broker diagnostic 在 durable inbox replay 阶段保存 review-required blocker，所以即使在 raw commit 后、normalization 前崩溃，重启重放也不会因无订单关联而清除阻塞。信息类通知不会伪造未知状态。所有发送与重放仍是人工显式编排，没有 retry、SELL、cancel 或新功能。

Paper-only evidence remains operator-dependent; there is no cryptographically authoritative broker account type proof. Private IB objects/internal state are trusted application internals, not a security sandbox against arbitrary Python mutation. The library connection bootstrap may cache account/position responses in its own IB object; Phase 3K never consumes them as local cash/NAV/position truth or synchronizes them into local accounting.

Review evidence and verdict: [Phase 3K Pre-Commit Review Report](phase3k_precommit_review_report.md).
