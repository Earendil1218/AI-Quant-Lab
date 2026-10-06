# Phase 3I — Execution Persistence and Recovery

## Scope / 范围

中文：基线 v0.10 / Phase 3H 已合并；3I 已通过 PR #10 合并（`574d1a5`）。目标是在未来开放自动执行之前建立 restart-safe identity 和经济去重。本阶段真实 IBKR place/cancel 仍无条件锁闭；没有后台 runner、网络轮询、自动重连或自动重发。SQLite 文件只对应一个明确的执行/账户作用域，应用调用方串行化 dispatch、状态更新与规划。

English: Baseline v0.10 / Phase 3H is merged; 3I is merged through PR #10 (`574d1a5`). The goal is restart-safe identity and economic dedup before any future automated execution. Real IBKR place/cancel remain unconditionally locked. There is no background runner, network polling, automatic reconnect or resend. One SQLite file represents one execution/account scope; the caller serializes dispatch, state writes and planning.

## Modules / 模块

| Module | Responsibility / 职责 |
|---|---|
| `infrastructure.codec` | Allowlisted schema-1 JSON, no pickle/dynamic import; Decimal strings and ISO datetime / 固定类型序列化 |
| `infrastructure.sqlite_execution` | Existing add/get/save protocol, durable claims, fill ledger, accounting markers and opaque broker evidence / SQLite 基础设施 |
| `execution.recovery` | Pure classification of existing lifecycle states / 纯恢复分类 |
| `execution.reconciliation` | Pure conservative assessment using existing BrokerOrderObservation / 复用快照类型核对 |
| `broker.ibkr.recovery` | Persist old-session bindings/raw callbacks; rebuild existing normalizer / 原始回调和身份恢复 |
| `application.paper_runner` | Explicit plan, prepare, dispatch, consume, recover and account calls / 薄应用编排 |

中文：domain 不导入 sqlite。原有内存 repository、AttemptClaims、Trading Fill、backtest API 均保留。新增持久化实现比内存实现更严格：累计成交必须完全由 Fill 支撑；已保存的请求、授权、broker identity 和成交前缀不可覆盖。现有历史数量快照若没有 Fill 不能直接迁入该 store。

English: Domain modules do not import sqlite. Existing memory repositories, AttemptClaims, Trading Fill and backtest APIs remain available. Persistence deliberately adds stricter checks: cumulative economics require complete fills; stored requests, authority, broker identity and the fill prefix cannot be overwritten. Legacy quantity-only snapshots cannot be imported without execution evidence.

## Schema / 数据模型

Database `PRAGMA user_version=2`; payload `schema=1`. Version 1 is explicitly rejected: the new ownership, planning and resolution invariants require a reviewed migration, which is not implemented.

| Table | Durable facts / 持久化事实 |
|---|---|
| `executions` | ClientOrderId PK, version, typed full aggregate JSON; includes state, request, authorization, timestamps, broker identity, fills; remaining quantity remains derived / 完整 aggregate，剩余数量派生 |
| `claims` | `(id, operation)` PK, exact consumed order snapshot; no delete/release API / 一次性消费快照 |
| `fills` | Acceptance sequence, unique fill identity, unique optional broker execution identity, order FK, full economic fill / 成交及全局作用域去重 |
| `accounting` | Unique accounted fill identity FK / 已记账成交标记 |
| `metadata` | Immutable initial cash / 不可重置的初始现金 |
| `observations` | Original payload, reason, correlation_key, resolved_at, resolved_by / 原始观察与定向解除审计 |
| `planning` | One-use planning id, revision, exact plan/risk payload and bound order / 一次性规划绑定 |
| `scoped_ownership` / `permanent_ownership` | SQL-enforced bidirectional ownership / 双向唯一归属 |
| `execution_families` | Account-scoped family and exact execution/order / 跨会话修正族 |
| `evidence` | Adapter-owned namespaced identity payloads, compare-and-swap replacement / adapter 身份快照 |
| `inbox` | Ordered raw callback payloads and consumed flags / 原始回调与处理标记 |

中文：使用 Python 标准库 sqlite3，无 ORM、外部服务或 event sourcing framework。每个操作独立连接，`BEGIN IMMEDIATE`、foreign keys、`synchronous=FULL`；事务异常整体 rollback，连接始终关闭。没有把数据库事务跨越 broker I/O。这里的持久性依赖正常的本地 SQLite/文件系统保证；不提供损坏修复、备份或 HA。

English: Uses standard-library sqlite3 without an ORM, service or event-sourcing framework. Each operation owns a connection with `BEGIN IMMEDIATE`, foreign keys and `synchronous=FULL`; exceptions roll back and connections close. Database transactions never span broker I/O. Durability relies on normal local SQLite/filesystem guarantees; corruption recovery, backups and HA are not provided.

中文：Decimal 编码为字符串，float 不允许进入 codec。datetime 使用 ISO 格式保存 offset 与 fold，沿用已有 domain 的 aware/naive 区分，不把 naive 自动解释为本地时区。经济成交时间与本地 applied_at 保持分离；应用时间必须不早于当前状态或观察接收时间。

English: Decimal uses strings; the codec rejects floats. Datetimes preserve ISO offsets and fold, retaining the existing aware/naive distinction without assuming a local timezone. Economic execution time remains distinct from local applied_at, which must not precede current state or observation receipt.

## Transactions / 事务

1. **Order and fill transaction / 订单与成交事务**: load aggregate → check expected version → pure observation application → `UPDATE ... WHERE id=? AND version=?` → insert/verify fill identities → retain observation → commit. A conflict or failure rolls back state, dedup and observation together. Duplicate committed observations do not regress lifecycle; fill replay with changed economics raises.
2. **Claim transaction / claim 事务**: validate exact saved authorized pending snapshot → verify operation unused → insert unique claim → commit **before** adapter allocates identity or enters transport. Concurrent claims allow one winner. No restart/reset releases the claim.
3. **Accounting transaction / 记账事务**: reconstruct initial cash plus fills in durable acceptance order → validate with existing `PortfolioState.apply_fill` → insert unique accounting markers → commit. No external mutable portfolio is updated before commit. `load_portfolio` reconstructs only accounted fills. An execution/accounting crash gap remains visible and `account_pending` explicitly closes it once. Failed cash/position validation preserves the gap.
4. **Raw callback boundary / 回调边界**: append raw input and commit before normalization; persist identity binding with compare-and-swap; reconstruct the existing normalizer from saved old-session evidence. Apply emitted neutral observations transactionally. Mark a fixed inbox batch consumed only after all observations commit and execution/commission pairs are complete. Crash before the marker means replay, not economic duplication.

中文：callback 持久化边界从 `PersistentIBKRInbox.append` 成功返回开始；网络接收但尚在 transport 内存队列中的事件仍可能丢失。本阶段无在线 ingestion loop，未来必须通过 broker 查询补齐该边界之前的缺口。异常 raw callback 保留并使 replay 失败；无静默丢弃或自动“修复”。

English: The durable callback boundary begins when `PersistentIBKRInbox.append` returns successfully. Events received only into the transport memory queue can still be lost. No online ingestion loop is supplied; future broker queries must cover gaps before this boundary. Invalid raw callbacks remain stored and fail replay; they are not silently discarded or repaired.

## Crash windows / 崩溃窗口

| Window | Restart behavior / 重启行为 |
|---|---|
| A: before claim | Saved SUBMISSION_PENDING without a claim is ATTEMPT_ALLOWED; caller may explicitly attempt with valid authority / 无 claim 可显式首次尝试 |
| B: claim committed, before transport | Original state retained, recovery action RECONCILIATION_REQUIRED; claim prevents resend / 要求核对，不释放 claim |
| C: transport entered, ack not persisted | Same conservative rule, even if transport returned; known DELIVERY_UNKNOWN may be saved as UNKNOWN / 禁止重发 |
| D: ack persisted | Restore broker identity, lifecycle/version and authority exactly; existing order is not recreated / 恢复既有订单 |
| E: fill persisted, before accounting | Unique fill survives; pending accounting is explicit; account once and reconstruct portfolio / 补记一次 |

中文：RecoveryAction 是恢复建议，不是新 lifecycle。`list_recovery_candidates()` 包括所有非终态；终态仍可能有未记账成交或未决回调，所以 runner 单独检查这些缺口。prepare 的创建、授权和 pending 保存是三个既有转换；中间崩溃保留 CREATED/AUTHORIZED 并阻止新规划，不会自动跳过授权或发送。

English: RecoveryAction is a classification, not a new lifecycle. `list_recovery_candidates()` includes all nonterminal orders. Terminal orders can still have accounting or callback gaps, which the runner checks separately. Preparation saves creation, authorization and pending as three existing transitions; a crash between them retains CREATED/AUTHORIZED and blocks new planning rather than bypassing authority or sending.

## Reconciliation / 核对

中文：复用 `BrokerOrderObservation`；`assess_reconciliation` 无 I/O、无状态修改，输出 CONSISTENT、ACKNOWLEDGEMENT_AVAILABLE、ECONOMIC_EVIDENCE_REQUIRED、STALE、MISSING、UNKNOWN 或 CONFLICT。ACKNOWLEDGEMENT_AVAILABLE 只是证据判断，仍须显式应用已验证观察。broker quantity/平均价格不替代真实 execution 与 commission。MISSING 或 UNKNOWN 永远不授权 retry；未提供自动 resend API。

English: Reuses `BrokerOrderObservation`. `assess_reconciliation` performs no I/O or mutation and returns CONSISTENT, ACKNOWLEDGEMENT_AVAILABLE, ECONOMIC_EVIDENCE_REQUIRED, STALE, MISSING, UNKNOWN or CONFLICT. An available acknowledgement is evidence only and must be applied explicitly. Broker quantity/average price never replace actual executions and commissions. MISSING and UNKNOWN never authorize retry; there is no automatic resend API.

中文：较旧状态观察不回退较新本地事实；迟到 Fill 仍通过严格经济身份去重接受。未决观察持久化且普通 ack 不清除。仅与已接受 Fill 精确关联的 WAITING_FOR_COMMISSION 可定向解除；其他未决 latch 没有通用解除 API，仍需要未来明确设计的人工核对处置；这种保守停机是已知限制，不能直接删除数据库/claim 作为恢复方法。

English: Older status observations cannot regress newer facts; late fills still use strict economic dedup. Unresolved observations persist and ordinary acknowledgements do not clear them. Only WAITING_FOR_COMMISSION records correlated with accepted fills can resolve. Other uncertainty has no blanket clearing API and requires a future explicitly designed review mechanism. This conservative stop is a known limitation; deleting the database or claims is not recovery.

## Runner and limits / Runner 与限制

中文：`PaperRunner.plan` 委托现有 sizing/planning/risk；`prepare` 消费显式 SubmissionAuthorization；`dispatch` 只委托 adapter 并保存不确定结果；`consume`/`consume_inbox` 保存观察；`account_pending` 显式记账。构造器检查同一数据库的持久化 claim。IBKR composition 使用 `PersistentIdentityRegistry`，一个应用作用域中共享 registry 并串行调用。旧 generation 的映射只供恢复证据，不自动转换为新连接权限。

English: `PaperRunner.plan` delegates sizing/planning/risk; `prepare` consumes explicit SubmissionAuthorization; `dispatch` delegates the adapter and saves uncertain outcomes; `consume`/`consume_inbox` persist observations; `account_pending` explicitly accounts. Construction requires durable claims from the same database. IBKR composition uses a shared PersistentIdentityRegistry with serialized application calls. Old-generation mappings are evidence, not authority in a new connection.

中文：未实现审批 workflow、自动取消编排、周期/组合 reconciliation、broker 查询补齐、完整未完成订单净额规划、通用清除未决事件、自动重试、监控告警、生产审计工具、跨进程协调、分布式 worker、HA、Live/期权执行。当前只有并发 claim 的本地数据库竞争测试；不能据此声称整个系统支持多进程。

English: Approval workflows, cancellation orchestration, periodic/portfolio reconciliation, broker-query recovery, full outstanding-order netting, blanket unresolved-event clearing, automatic retry, monitoring/alerts, operational audit tooling, multi-process coordination, distributed workers, HA and live/options execution remain excluded. Local concurrent-claim tests do not establish multi-process system support.

## Verification / 验证

Tests use tmp_path databases, fresh repository/session objects after deterministic failures, fake transports and the unchanged network/order blocking fixture. Coverage includes A–E, execution-first and commission-first restart pairing, cross-order identity conflicts, SQL rollback, stale writers/registries, one-winner concurrent claims/dispatch, old ack replay, accounting replay, inbox gaps and the still-locked real transport.

测试仅使用临时数据库、故障后重建对象、fake transport 和既有网络拦截 fixture；不访问 TWS，不创建项目数据库。完整命令与 README 一致，另用内存 compile 和 import smoke 验证，不生成 pyc。

## Pre-commit safety fixes

- **Planning freshness**: `application.planning.PlanningTicket` replaces the unpublished runner tuple API. `plan` returns a persisted ticket; `prepare(ticket, authorization, *, prepared_at=...)` consumes it once. Its SHA-256 portfolio revision covers immutable initial cash, accounted fills in acceptance order and the accounting policy identifier. The database binds the exact plan and risk decision; a copied old risk decision cannot be attached to a new ticket. Preparation validates freshness and atomically creates/binds the order. Dispatch validates again, and claim repeats the check inside its transaction. Stale tickets raise `StalePlanningDecision` before transport.
- **Raw quantities**: IBKR callbacks can contain integral floats such as `100.0`. The broker inbox canonicalizes only shares/filled/remaining/quantity to integers using strict integral validation before persistence. Fractional, nonfinite and boolean quantities fail; the generic codec still rejects all floats.
- **Ownership**: API identity is scoped by generation/client ID; permanent identity by account/permId. SQL primary keys prevent two owners, with forward uniqueness preventing local remapping in the same scope. Evidence and ownership commit atomically; independent registries and concurrent writers cannot bypass this invariant. Different sessions may use new API IDs; different accounts may use the same permId.
- **Corrections**: Numeric execution suffixes share the prefix family, scoped by account, independent of generation. Validated first evidence reserves the durable family before economic application; exact replay remains valid, a different revision raises `CORRECTION_REQUIRES_RECONCILIATION`. The raw batch stays unconsumed and cash, position, fill quantity and commission remain unchanged.
- **Resolution**: `EXECUTION_PENDING.pending_execution_id` supplies neutral execution correlation. Accepted fee-complete fills resolve only the same order/execution's `WAITING_FOR_COMMISSION` observations in the observation transaction, including late pending replay. Original payload and unresolved flag remain for audit; active queries use `resolved_at IS NULL`. UNKNOWN and connection-loss evidence are not cleared by later fills or acknowledgements.
- **Accounting**: `infrastructure.accounting` uses explicit Decimal precision 50, ROUND_HALF_EVEN, fixed exponent limits and traps for Inexact/Rounded as well as invalid arithmetic. Both reconstruction and accounting use this context without mutating the caller's context. No cent quantization is introduced; precision loss fails before accounting markers commit.

Verification adds 35 cases: the full suite is 537 passed / 0 failed / 1 skipped. Two real subprocess `os._exit` tests cover committed claim survival and fill-before-accounting recovery; fresh processes prove duplicate claim rejection and one-time booking. Five selected claim/identity/replay/version/freshness regressions each passed 50 fresh pytest runs (250 executions). These are process-crash tests, not machine-power-loss or multi-process coordination guarantees.

中文：上述修复将未发布的 runner API 改为持久化一次性票据，在 prepare、dispatch、claim 校验 freshness；仅 broker 数量允许合法整股 float 转整数。身份双向唯一约束与 evidence 同事务；修正族按账户跨会话持久化，冲突保留原始批次且不改变经济状态。佣金等待仅按订单与 execution 精确解除，保留审计，不解除其他 UNKNOWN。记账采用 precision=50、ROUND_HALF_EVEN 与精度损失 trap，不按分自动舍入。两个真实子进程退出测试不构成断电或多进程协调保证。

Phase 3J extends this existing evidence/transaction seam with read-only query reconciliation; see [IBKR reconciliation](ibkr_reconciliation.md). 3J 不改变已有 claim、Fill 或记账语义。

## Phase 3K integration / 受控执行扩展

Phase 3J 已通过 PR #11 合并（`bdf08e8` / `a74e0cd`）。Phase 3K 基于该合并基线增加独立默认锁闭的 `PaperExecutionTransport` 与显式 application orchestration；以上 3H–J 的全锁闭描述是历史阶段范围，ReadOnlyIBKRTransport 本身仍然只读。

Online Paper integration is opt-in only. Current-session exact-account human confirmation, two explicit caller opt-ins, persisted planning/risk/SubmissionAuthorization, SQLite claim and durable ownership are all required. Startup/fresh reconciliation uses the existing strong-identity comparison and evidence store; MATCH never clears UNKNOWN or creates a fill/approval. Fee-complete full fills can audit-resolve matching pending/held/completion hints only; identity/quantity conflicts and other uncertainty remain blocked.

真实 BUY/MKT 受控开放；真实 SELL 因本地库存不等于 broker 库存保持锁闭，真实 cancel 也保持锁闭。没有自动重试/重连、Live、自动策略或账户同步；配置与 session evidence 不构成 broker 账户类型证明，仍需独立人工核验。详见 [完整执行链路与人工验收](paper_execution_loop.md)。开发验证全部离线，未调用真实 TWS/Paper order。

## Pre-commit safety audit / 提交前安全审查

发送 scope 已改为内部 `_dispatch_scope`，入口验证尚未消费的 durable claim，避免用已消费 claim 重入并绕过 adapter；公开 `place/next_order_id` 没有内部 scope 时仍拒绝。边界使用确切 OrderSide.BUY，并重新核对获授权 instrument 与 spec。连接期 disconnect、connectivity/recovery notice 或未知诊断永久退役该 generation，连接返回不得恢复权限。

未知 broker diagnostic 在 durable inbox replay 阶段保存 review-required blocker，所以即使在 raw commit 后、normalization 前崩溃，重启重放也不会因无订单关联而清除阻塞。信息类通知不会伪造未知状态。所有发送与重放仍是人工显式编排，没有 retry、SELL、cancel 或新功能。

Paper-only evidence remains operator-dependent; there is no cryptographically authoritative broker account type proof. Private IB objects/internal state are trusted application internals, not a security sandbox against arbitrary Python mutation. The library connection bootstrap may cache account/position responses in its own IB object; Phase 3K never consumes them as local cash/NAV/position truth or synchronizes them into local accounting.

Review evidence and verdict: [Phase 3K Pre-Commit Review Report](phase3k_precommit_review_report.md).
