# Phase 3K Pre-Commit Review Report

## 1. Baseline

- Branch: `feature/phase-3k-ibkr-paper-execution-loop`.
- Starting SHA / current HEAD / local main / existing origin-main tracking ref: `bdf08e87804e0cc70a220e64b0dc97861f203dd3`.
- 未 fetch；结论针对本地现有 Git refs，不声称重新验证远端当前最新状态。
- Initial status: 13 tracked modified files, 5 untracked Phase 3K files; no staged changes. No unrelated changes found.
- Initial tracked diff: 13 files changed, 216 insertions(+), 36 deletions(-). Untracked files are excluded from ordinary git diff/stat.
- Reverified pre-audit suite: **637 passed / 0 failed / 1 skipped**.
- Windows Python alias remains unusable; verification uses `.venv311/Scripts/python.exe`.
- Full tracked diff, name-status, untracked content, HEAD/main refs were inspected before production code changes. Existing work was preserved.

Initial untracked files:

```text
application/paper_integration.py
broker/ibkr/paper_transport.py
docs/paper_execution_loop.md
docs/phase3k_development_report.md
tests/test_phase3k_paper_loop.py
```

## 2. Scope Reviewed

- Production side effect: `broker/ibkr/paper_transport.py`, `adapter.py`, `config.py`, `transport.py`, `session.py`, `mapping.py`, `connection.py`, package exports.
- Raw evidence: `events.py`, `models.py`, `errors.py`, `recovery.py`, PersistentIdentityRegistry and PersistentIBKRInbox.
- Application: `application/paper_runner.py`, `paper_integration.py`, planning contracts.
- Durable domain/storage: `execution/dispatch.py`, `models.py`, `lifecycle.py`, `observations.py`, `recovery.py`, `broker_state.py`; `infrastructure/sqlite_execution.py`, reconciliation store and accounting/codec seams.
- Tests: all original 46 Phase 3K cases; correlated 3H/3I/3J mapping, authorization, persistence, subprocess recovery, accounting, raw callback and reconciliation coverage; `tests/conftest.py` and existing read-only integration test.
- Configuration/secrets: `.env.example`, config, new tests and documentation; no new real username/password/token/account credentials, real account IDs or machine secrets found. `DU_TEST` / `U1234567` are deliberately fictional test identifiers, not deployment inputs.
- Documentation: README, current_status, roadmap, decisions, ibkr_execution, execution_recovery, ibkr_reconciliation, paper_execution_loop and development report. Phase 3J is correctly marked merged in PR #11.

No SELL/cancel capability, Phase 3L implementation, unrelated refactor, dependency change, schema migration or broker/domain financial contract change was introduced.

## 3. Safety Findings

### Paper-only / Live Trading boundary

没有受支持的 Live execution path。PAPER mode、config side-effect intent、本地固定端点、exact independently verified account allowlist、额外 DU restriction、current session host/port/client ID/managed accounts/generation、当前 generation 的独立人工确认均必须满足。仅改 port 或 account 不能满足这组约束；构造快照改变也拒绝。

7497 / DU / client ID / readonly 参数不是 Paper 证明。系统没有 cryptographically authoritative broker account type proof，仍信任真实的人工独立核验与 allowlist；不承诺识别虚假人工声明、被替换的 broker 或任意重配 TWS。没有实际 Live 测试。

### Default lock / explicit opt-in / public paths

默认 DISABLED、无 side-effect opt-in；构造、import、初始化、risk calculation 和 runner startup 均不发送。PaperExecutionTransport 必须显式传入 config 构造；可以构造 disabled inert object，这不授予连接或发送权限。发送连接要求两个显式布尔 True 和当前会话人工确认，配置/环境残留不能代替它们。

ReadOnlyIBKRTransport 未修改，ID/place/cancel 永久锁闭。唯一生产 `IB.placeOrder` 调用位于 Paper transport 的 guarded place 方法。公开 place/next_order_id 无内部 scope 时拒绝；新的 `_dispatch_scope` 仅内部使用，并在入口拒绝已经消费的 claim。内部 scope 不能跳过当前持久化 intent、authority、BUY/mapping、session、claim/ownership 和 blocker 检查。

`_ib` 和其他 underscore internals 是受信任的 Python 应用内部对象，不是对任意恶意 Python 修改的安全 sandbox。没有提供公开裸 IB/send handle。

### BUY-only / cancel

真实边界仅接受 exact OrderRequest 与 `OrderSide.BUY`。获授权 instrument、spec、qualified contract、durable binding 和 mapped order 再次匹配。SELL 在 claim/ID/API 之前拒绝；direct adapter、runner、真实持久化恢复、并发与 mutated-side snapshot 都有实际 side-effect count 证据。

Mapping 层为旧 offline API 保留 BUY/SELL 的精确映射，不会把非法 side 静默变成 BUY。真实 cancel 永久抛安全错误；没有任何生产 cancelOrder 调用。synthetic Trade cancel/error 不会成为 broker confirmation。

### Human authorization

Risk PASS 不创建 SubmissionAuthorization。Planning ticket 与 risk decision 不是发送权限；独立 caller-created authorization 绑定 exact request/client ID，并先保存 authorized/pending intent。直接 adapter 也必须具有同一数据库的持久化规划、授权快照和 claim。

### Durable claim / exactly-once attempt

Non-consuming validation/mapping/qualification/preparation/current-session preflight 先完成，然后 atomic SQLite claim、ID allocation、persistent ownership、verify_current/final validation，最后 API entry。准备失败不消费 claim/ID；unsupported SELL、stale session、account mismatch 都在 claim 前失败。

Claim 无 release/reset/reclaim API，消费后 NOT_SENT 也不重试。Scope entrance 不能重入已消费 claim。并发测试检查实际 fake IB.placeOrder count=1 与仅一次 ID allocation；包括同一 transport 锁和两个独立 Paper transports 竞争同一 SQL claim。

这是持久化 at-most-once submission-attempt 语义，不是 broker delivery/economic execution 的分布式 exactly-once 保证；SQLite 与 broker 没有跨系统原子事务。已消费但未发送的 crash window 仍需 review，不能猜测安全重发。

### UNKNOWN / recovery

API entry 后 exception/timeout/disconnect 均是 UNKNOWN/uncertain；底层即使抛出名为 PaperNotSentError 的异常，也不能伪造 pre-entry NOT_SENT proof。API 返回不是 ack/fill。

连接期间及连接后 session-loss、recovery notice、未知 diagnostic 都永久退役 generation；连接返回不能恢复它。Restart、fresh instance、reconnect、runner dispatch、reconciliation 或 recovery list 均不能释放旧 claim。UNKNOWN → block → observe/reconcile/manual review，没有自动 resend。

### Callbacks / accounting

RawCallbackWrapper 捕获真实 openOrder/orderStatus/execDetails/commissionReport/error/disconnect；不消费合成 Trade 状态。Raw inbox 在 lifecycle 前提交，lifecycle/fill 在 accounting 前提交；pending accounting 和 crash recovery 保留既有语义。

重复 execId/callback/fill/accounting 幂等，费用必须来自真实 commissionReport，placeholder/未知金额不能伪造。foreign/manual/conflicting identity 不接管，原始证据保留并阻断。

未知 diagnostic 不仅退役当前 generation，也在 durable inbox replay 中保存固定 review-required blocker。即使 crash 在 raw commit 后、normalization 前，generic recovery replay 仍重建 blocker，不能把无关联 error 当作可忽略并恢复规划。识别的信息类通知不会伪造 UNKNOWN。

费用完整 full fills 仅审计解决确切身份匹配的 pending/held/completion hints；原记录保留，UNKNOWN、disconnect、数量冲突和其他不确定性不被清除。

### Reconciliation / local vs broker portfolio

3J strong identity、foreign non-adoption、durable mismatch blocker 与 no automatic local repair 保持。MATCH 不清除 UNKNOWN、不生成 fill/authorization、不覆盖本地现金/持仓。Blocked store/inbox/observation/accounting/recovery 禁止 planning/dispatch。

范围仍是 execution/order/fill，不是 account/portfolio reconciliation。没有读取或同步 broker NAV/Cash/Buying Power/Positions/Average Cost/P&L 到本地会计。固定版本 ib-insync 的连接 bootstrap 会在自身 IB 对象内缓存账户/持仓响应；这不构成 Phase 3K 的 domain/accounting 同步，也未被用作 SELL 权限。

### Online harness / normal tests

Harness 不是自动收集的真实下单 pytest、CLI 或 startup hook；需要显式 symbol/quantity 对应的 intent/sizing/valuation/authorization、当前 generation confirmation、两个调用 opt-in 和两个环境 gate。没有自动选择标的/数量，没有改变 TWS 设置，没有 retry/cancel/reconnect。

默认 tests fixture 禁用真实 IB/Client connect/placeOrder/cancelOrder 和 socket connection。既有 read-only integration 仅显式环境 opt-in 时可连接，其真实订单方法仍禁用；这不同于手工 Paper side-effect harness。本轮 full pytest 进程明确把 read-only integration gate 设为 0，不运行任何在线测试。

## 4. Issues Found

| Severity | ID | 原问题与可复现证据 | 当前状态 |
|---|---|---|---|
| Critical | — | None | None |
| High | H1 | Public dispatch_scope 可带入已消费 claim，在 pre-entry ID failure 后再次进入 ID/send preparation；新 regression 在修复前失败 | Fixed |
| High | H2 | connect 期间 error/disconnect 的失效状态被随后 _valid=True 覆盖；两种 handshake-loss regression 修复前均失败 | Fixed |
| High | H3 | 无关联 unknown error 可被消费而不留下 durable readiness blocker；raw-commit/replay crash window 同样需要阻塞 | Fixed；live ingestion 与 generic restart replay 均覆盖 |
| Medium | M1 | 最终 real boundary 未重验授权 instrument/spec 一致性；手工组合不一致 spec/contract 可进入 fake API | Fixed；regression 修复前失败 |
| Low | L1 | 原 SELL 测试仅绕过 planning 检查测 preflight，不能证明 genuine planned/recovered/direct/concurrent SELL 行为 | Fixed；新增真实 SQLite planning/risk/authorization 测试 |
| Low | L2 | 新边界部分内部状态/接口缺少类型，package/place docstrings 与默认锁/精确 entry 语义过时 | Fixed；补边界类型与文档 |

所有上述 functional blockers 已修复；没有遗留 Critical/High/Medium blocker。没有隐藏原始失败证据；637-case baseline 未发现旧测试失败，新增回归专门复现其未覆盖的缺口。

## 5. Fixes Made

1. Public dispatch_scope 改为 internal `_dispatch_scope`；scope admission 在任何 token-like use 前验证 fresh unconsumed submission intent，adapter/runner 检测与测试同步更新。
2. 增加永久 `_retired` latch；connect 返回前检查，disconnect/connectivity/recovery/unknown diagnostics 不能恢复旧 generation，close 也使其失效。
3. Final transport preflight 仅接受 exact BUY request，复用 map_contract 重验获授权 instrument/spec，一致性错误在 real API 前拒绝。
4. 在 PersistentIBKRInbox replay 中持久化未知诊断 blocker，覆盖 raw commit 与 normalizer 之间的 crash window；信息类通知保持原语义。没有伪造 broker rejection/confirmation。
5. 补 scope re-entry、连接期失效、final spec mismatch、genuine planned/recovered/concurrent SELL、mutated side、risk-without-human approval、两个真实边界 fake transports 的 SQL claim race、未知诊断和 crash replay 等必要回归。
6. 补关键 transport state/interface 类型，修正文档与 historical-vs-current validation 表述，明确 Paper trust limit、BUY-only、SELL/cancel 锁闭和 library bootstrap/domain accounting 的区别。

未改交易范围、依赖、schema、领域经济模型或已合并 3A–J 的 public APIs。

## 6. Tests

- Pre-audit full suite: **637 passed / 0 failed / 1 skipped**.
- Original Phase 3K cases: 46.
- Post-review Phase 3K cases: **60 passed / 0 failed**; +14 focused regression instances.
- Correlated targeted suite: **223 passed / 0 failed** (Phase 3K, adapter, runner, 3J reconciliation, IBKR safety, SQLite persistence, 3I safety fixes).
- Final full suite: **651 passed / 0 failed / 1 skipped**, +14 versus the 637-case pre-audit baseline.
- Compile: **107 Python files PASS**; import: **70 production modules PASS**, with real network/order entrypoints disabled and zero attempted external I/O.
- git diff --check: **PASS**. Exact commands/stat/status are recorded below.
- Concurrency uses Barrier and actual call counters; harness deadline test uses controlled monotonic time. No sleep-based race tests.
- Single skip is the existing opt-in read-only integration; no real network/order test was enabled.

## 7. Side Effects

| Action | This review |
|---|---|
| Connected to real TWS | **NO** |
| Real Paper order / cancellation | **NO** |
| Live order | **NO** |
| Commit / push / PR / merge | **NO** |
| Reset / clean / discard / rebase / amend / force push / branch deletion | **NO** |
| Unlock SELL/cancel / implement Phase 3L | **NO** |

IB calls in regression tests were external in-memory fakes, while real adapter/SQLite/registry/wrapper/inbox code was exercised. Compile/import smoke did not connect or send.

## 8. Git

All changes remain unstaged/uncommitted in the original feature branch; HEAD remains the starting main SHA. No push, PR or merge was performed. Initial and final status show only Phase 3K implementation/tests/documentation and necessary safety changes. Final tracked stat/name-status and untracked list are recorded below; ordinary diff stat excludes untracked files.

## 9. Residual Limitations

- SELL locked; cancel locked.
- No broker account/cash/NAV/position synchronization, no broker position truth.
- No automatic strategy execution, scheduler, auto selection, streaming loop or account/portfolio reconciliation.
- Independent human Paper verification is a trust input; no cryptographic broker account-type proof.
- Private Python/broker internals are trusted; not an arbitrary-code security sandbox.
- One-process/account-scope application serialization; no multi-process coordination, distributed exactly-once, broker/SQLite atomic commit or HA.
- No generic clearing/operator resolution of true UNKNOWN/reconciliation blockers; review remains necessary.
- Malformed unencodable raw callback contents may remain in process memory while the durable failure latch survives; no promise of durable invalid payload content.
- No real online acceptance evidence. Future real Paper acceptance still needs separate explicit user authorization and TWS/operator preparation.

## 10. Final Verdict

**READY FOR COMMIT** within the reviewed trust model and BUY-only scope; no unresolved review blocker.

**Phase 3K can be committed as a BUY-only controlled IBKR Paper Execution Loop Foundation.**

This verdict is code-review readiness, not deployment/online trading authorization and not proof of broker Paper account type. Changes have deliberately NOT been committed, pushed, made into a PR or merged.

## Final Verification Snapshot

Full test command (read-only integration explicitly disabled for this process):

```powershell
$env:RUN_IBKR_PAPER_INTEGRATION='0'
.\.venv311\Scripts\python.exe -m pytest -q
```

Result: **651 passed / 0 failed / 1 skipped**. Targeted correlated suite: **223 passed**.

### git diff --stat (tracked files only)

```text
 README.md                          | 22 ++++++++---
 application/paper_runner.py        | 78 ++++++++++++++++++++++++++++++++++++++
 broker/ibkr/__init__.py            |  5 ++-
 broker/ibkr/adapter.py             | 29 +++++++++++---
 broker/ibkr/config.py              |  2 +-
 broker/ibkr/events.py              |  3 +-
 broker/ibkr/recovery.py            |  6 +++
 docs/current_status.md             | 45 +++++++++++++---------
 docs/decisions.md                  | 24 ++++++++++++
 docs/execution_recovery.md         | 18 +++++++++
 docs/ibkr_execution.md             | 18 +++++++++
 docs/ibkr_reconciliation.md        | 23 ++++++++++-
 docs/roadmap.md                    | 20 +++++++++-
 infrastructure/sqlite_execution.py | 21 ++++++++++
 14 files changed, 277 insertions(+), 37 deletions(-)
```

### git diff --name-status

```text
M	README.md
M	application/paper_runner.py
M	broker/ibkr/__init__.py
M	broker/ibkr/adapter.py
M	broker/ibkr/config.py
M	broker/ibkr/events.py
M	broker/ibkr/recovery.py
M	docs/current_status.md
M	docs/decisions.md
M	docs/execution_recovery.md
M	docs/ibkr_execution.md
M	docs/ibkr_reconciliation.md
M	docs/roadmap.md
M	infrastructure/sqlite_execution.py
```

### git status --short

```text
 M README.md
 M application/paper_runner.py
 M broker/ibkr/__init__.py
 M broker/ibkr/adapter.py
 M broker/ibkr/config.py
 M broker/ibkr/events.py
 M broker/ibkr/recovery.py
 M docs/current_status.md
 M docs/decisions.md
 M docs/execution_recovery.md
 M docs/ibkr_execution.md
 M docs/ibkr_reconciliation.md
 M docs/roadmap.md
 M infrastructure/sqlite_execution.py
?? application/paper_integration.py
?? broker/ibkr/paper_transport.py
?? docs/paper_execution_loop.md
?? docs/phase3k_development_report.md
?? docs/phase3k_precommit_review_report.md
?? tests/test_phase3k_paper_loop.py
```

### Untracked files

```text
application/paper_integration.py
broker/ibkr/paper_transport.py
docs/paper_execution_loop.md
docs/phase3k_development_report.md
docs/phase3k_precommit_review_report.md
tests/test_phase3k_paper_loop.py
```

### Phase 3K test instances after review

```text
tests/test_phase3k_paper_loop.py::test_double_opt_in_required_before_connect[False-False]
tests/test_phase3k_paper_loop.py::test_double_opt_in_required_before_connect[True-False]
tests/test_phase3k_paper_loop.py::test_double_opt_in_required_before_connect[False-True]
tests/test_phase3k_paper_loop.py::test_double_opt_in_required_before_connect[1-True]
tests/test_phase3k_paper_loop.py::test_default_and_direct_transport_cannot_send
tests/test_phase3k_paper_loop.py::test_confirmation_exact_current_account[changes0]
tests/test_phase3k_paper_loop.py::test_confirmation_exact_current_account[changes1]
tests/test_phase3k_paper_loop.py::test_confirmation_exact_current_account[changes2]
tests/test_phase3k_paper_loop.py::test_confirmation_exact_current_account[changes3]
tests/test_phase3k_paper_loop.py::test_endpoint_mismatch_does_not_claim[host-remote]
tests/test_phase3k_paper_loop.py::test_endpoint_mismatch_does_not_claim[port-7496]
tests/test_phase3k_paper_loop.py::test_endpoint_mismatch_does_not_claim[clientId-9]
tests/test_phase3k_paper_loop.py::test_session_and_config_mutation_fail_closed[account]
tests/test_phase3k_paper_loop.py::test_session_and_config_mutation_fail_closed[generation]
tests/test_phase3k_paper_loop.py::test_session_and_config_mutation_fail_closed[disconnect]
tests/test_phase3k_paper_loop.py::test_session_and_config_mutation_fail_closed[config]
tests/test_phase3k_paper_loop.py::test_preparation_failures_preserve_claim[qualification]
tests/test_phase3k_paper_loop.py::test_preparation_failures_preserve_claim[mapping]
tests/test_phase3k_paper_loop.py::test_preparation_failures_preserve_claim[late_preflight]
tests/test_phase3k_paper_loop.py::test_success_sends_once_and_restart_retains_claim
tests/test_phase3k_paper_loop.py::test_concurrent_duplicate_dispatch_is_one_attempt
tests/test_phase3k_paper_loop.py::test_before_api_failure_is_not_sent_but_claim_stays_consumed
tests/test_phase3k_paper_loop.py::test_after_api_entry_is_unknown_never_retried[timeout]
tests/test_phase3k_paper_loop.py::test_after_api_entry_is_unknown_never_retried[disconnect]
tests/test_phase3k_paper_loop.py::test_after_api_entry_is_unknown_never_retried[reserved_not_sent]
tests/test_phase3k_paper_loop.py::test_disconnect_and_reconciliation_block_new_planning
tests/test_phase3k_paper_loop.py::test_real_cancel_remains_locked_and_session_cannot_reconnect
tests/test_phase3k_paper_loop.py::test_raw_callbacks_fill_account_duplicate_and_fresh_match
tests/test_phase3k_paper_loop.py::test_pending_callbacks_block_planning_and_dispatch_without_claim
tests/test_phase3k_paper_loop.py::test_foreign_raw_order_is_retained_not_adopted
tests/test_phase3k_paper_loop.py::test_memory_claims_cannot_unlock_production_transport
tests/test_phase3k_paper_loop.py::test_invalid_paper_config_never_connects[mode-LIVE]
tests/test_phase3k_paper_loop.py::test_invalid_paper_config_never_connects[allow_side_effects-False]
tests/test_phase3k_paper_loop.py::test_invalid_paper_config_never_connects[port-7496]
tests/test_phase3k_paper_loop.py::test_invalid_paper_config_never_connects[paper_account_allowlist-value3]
tests/test_phase3k_paper_loop.py::test_late_pre_api_failure_after_claim_is_provably_not_sent
tests/test_phase3k_paper_loop.py::test_manual_harness_gates_cannot_be_inferred[False-False-True]
tests/test_phase3k_paper_loop.py::test_manual_harness_gates_cannot_be_inferred[True-False-True]
tests/test_phase3k_paper_loop.py::test_manual_harness_gates_cannot_be_inferred[True-True-False]
tests/test_phase3k_paper_loop.py::test_manual_harness_offline_full_loop_uses_supplied_authority
tests/test_phase3k_paper_loop.py::test_post_fill_completion_audit_never_clears_other_uncertainty
tests/test_phase3k_paper_loop.py::test_real_sell_is_locked_without_broker_inventory
tests/test_phase3k_paper_loop.py::test_repeated_fresh_matching_query_preserves_readiness
tests/test_phase3k_paper_loop.py::test_manual_harness_deadline_is_unknown_without_retry
tests/test_phase3k_paper_loop.py::test_live_account_identifier_cannot_connect_even_with_false_confirmation
tests/test_phase3k_paper_loop.py::test_broker_session_loss_retires_even_connected_socket
tests/test_phase3k_paper_loop.py::test_consumed_claim_cannot_reenter_transport_scope
tests/test_phase3k_paper_loop.py::test_loss_during_connect_cannot_restore_generation[error]
tests/test_phase3k_paper_loop.py::test_loss_during_connect_cannot_restore_generation[disconnect]
tests/test_phase3k_paper_loop.py::test_final_contract_spec_cannot_change_authorized_instrument
tests/test_phase3k_paper_loop.py::test_genuinely_planned_sell_never_consumes_claim_or_sends[adapter]
tests/test_phase3k_paper_loop.py::test_genuinely_planned_sell_never_consumes_claim_or_sends[runner]
tests/test_phase3k_paper_loop.py::test_genuinely_planned_sell_never_consumes_claim_or_sends[recovered]
tests/test_phase3k_paper_loop.py::test_genuinely_planned_sell_never_consumes_claim_or_sends[concurrent]
tests/test_phase3k_paper_loop.py::test_mutated_side_snapshot_cannot_bypass_saved_authority
tests/test_phase3k_paper_loop.py::test_risk_pass_without_human_authorization_has_no_send_capability
tests/test_phase3k_paper_loop.py::test_independent_paper_transports_race_on_one_durable_claim
tests/test_phase3k_paper_loop.py::test_uncorrelated_unknown_broker_error_is_a_durable_blocker
tests/test_phase3k_paper_loop.py::test_informational_broker_error_does_not_invent_uncertainty
tests/test_phase3k_paper_loop.py::test_unknown_diagnostic_replay_after_raw_commit_cannot_clear_blocker

60 tests collected in 0.14s
```
