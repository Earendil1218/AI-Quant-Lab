# Phase 3K Development Report

日期 / Date: 2026-10-06。状态：本地实现、未提交、待 review；没有真实在线验收。

## 1. 真实基线与中断恢复

- Branch: `feature/phase-3k-ibkr-paper-execution-loop`。
- Starting main SHA: `bdf08e87804e0cc70a220e64b0dc97861f203dd3`。
- 本地 main 与现有 `origin/main` tracking ref 一致；未 fetch，所以不声称重新验证远端最新状态。
- 最近五个 commits：`bdf08e8`（PR #11 merge）、`a74e0cd`（3J）、`574d1a5`（PR #10 merge）、`750d18e`（3I）、`6319e98`（PR #9 merge）。
- 首次基线：591 passed / 0 failed / 1 skipped；恢复后同样 591 passed / 0 failed / 1 skipped。
- 恢复检查发现分支已存在，`adapter.py` 已修改，`paper_transport.py` 已新增未跟踪；保留并继续，没有重建分支或丢弃工作。恢复时的 tracked diff 为 1 file / 18 insertions / 5 deletions；untracked transport 不包含在普通 diff stat 中。
- Windows `python` 别名不可运行；所有测试使用仓库 `.venv311/Scripts/python.exe`。

## 2. 修改与新增文件

Modified:

- `README.md`
- `application/paper_runner.py`
- `broker/ibkr/__init__.py`
- `broker/ibkr/adapter.py`
- `broker/ibkr/config.py`
- `broker/ibkr/events.py`
- `infrastructure/sqlite_execution.py`
- `docs/current_status.md`
- `docs/roadmap.md`
- `docs/decisions.md`
- `docs/ibkr_execution.md`
- `docs/execution_recovery.md`
- `docs/ibkr_reconciliation.md`

Added / untracked:

- `broker/ibkr/paper_transport.py`
- `application/paper_integration.py`
- `tests/test_phase3k_paper_loop.py`
- `docs/paper_execution_loop.md`
- `docs/phase3k_development_report.md`

## 3. 架构变化与最小修复

新增独立 PaperExecutionTransport，复用只读 transport 的 owned IB/raw wrapper、qualification、snapshot 和 queue。ReadOnlyIBKRTransport 未修改、真实订单锁仍在。adapter 新增可选 dispatch scope，旧 fakes/public signatures 保持兼容；生产 transport 强制 SQLite claims 和 PersistentIdentityRegistry 来自同一数据库。

PaperRunner 增加显式 startup、raw ingestion 和 fresh reconciliation 三个薄编排方法。人工 harness 是 application 函数，没有 scheduler、CLI dashboard、市场数据 loop 或自动 strategy trigger。没有 SQLite schema migration，没有修改 broker-neutral OrderRequest/Fill，也没有修改 ib-insync 0.9.86 固定版本策略。

恢复后修复了草稿中的不存在的 portfolio.quantity() 调用、claim 后误阻塞自身 attempt 和订单对象身份比较问题。新增 broker connectivity error 对 generation 的失效处理：1100/1101/1102 等通知不能恢复旧发送权限。

为完整处理真实回调，openOrder 已知 pending/held 状态与 orderStatus 对齐；SQLite 仅在费用完整 full fills 已证明 FILLED 且确切 broker identity/request 匹配时审计解决相关 pending/held/completion hints，保留原始 observation。UNKNOWN/断线/冲突不会被清除。

## 4. Paper transport 解锁与 explicit opt-in

构造不连接；配置默认 DISABLED，ReadOnlyIBKRTransport 永不解锁。新增 PaperExecutionTransport 要求：

1. 显式 PAPER config、allow_side_effects=True、本地 host、7497、独立非零 client ID、单一独立核验 exact allowlist。
2. 额外限制受支持账户 identifier 为 DU；这只是防御约束，不能单独作为 Paper 证明。明显 Live U identifier 即使有错误人工确认也拒绝。
3. 调用方传入两个独立布尔 True：integration_opt_in 与 side_effect_opt_in。
4. PaperSessionConfirmation 绑定当前 generation、确切账户、operator 与明确 TWS Simulated/Paper 核验声明。
5. 实际 session endpoint、managed accounts、generation 与构造快照一致。
6. 当前数据库已持久化该 session 的 startup reconciliation MATCH，且没有未决状态。

Harness 额外要求 `RUN_IBKR_PAPER_INTEGRATION=1` 与 `ALLOW_IBKR_PAPER_ORDER_SIDE_EFFECTS=YES`；环境变量本身不授予连接、人工审批或 submission authority。

信任限制：现有 Socket session evidence 没有可靠 broker 签发的 Paper/Live 类型证明。独立 allowlist 与人工 Paper 确认必须真实。程序拒绝 LIVE mode/Live port/非 DU identifier，但不能识别虚假确认、被替换的 broker 或任意重配 TWS 所声称的账户类型。

## 5. human authorization 独立性

Risk PASS 不生成 SubmissionAuthorization。runner.prepare 消费调用方独立提供、绑定确切 request/client ID 的授权，并持久化授权和 pending intent。transport 要求已保存的 planning/risk/authorization；环境 gate、connect、MATCH 和 runner 启动均不是授权。

Risk approval ≠ human approval ≠ submission authority ≠ execution result.

## 6. durable claim 时序与 side-effect boundary

Non-consuming validate → qualification → prepare_order → locked session/durable preflight → SQLite atomic permanent claim → allocate IBKR ID → persistent ownership → verify_current/final preflight → IB.placeOrder。

qualification/mapping/preflight 在 claim 前失败，不消费 claim，不分配 broker ID。claim 永不自动释放。ID 分配或身份保存失败，或 API 前的最后核验失败，返回可证明 NOT_SENT；已消费 claim 仍保留。

Paper transport 对同一 generation 串行化 dispatch；SQL 唯一 claim 是跨重启一次 attempt 的边界。持久化身份必须在真实 API 前完成。Order 比较使用 dataclass 字段，不能用 ib-insync Order 的对象身份相等判断。

## 7. UNKNOWN / timeout / disconnect

进入真实 IB.placeOrder 后，exception/timeout/同步断线均 DELIVERY_UNKNOWN，runner 保存 UNKNOWN。API 正常返回仅意味着边界返回，不代表 broker acknowledgement 或 fill。无 automatic resend/retry/reconnect。

Harness 有界等待未获得可靠终态时保存 UNKNOWN；不重发、不自动 cancel。disconnect 或 broker session-loss/recovery notice 使旧实例失效；新对象/runner/session 不能释放旧 durable claim。Crash 窗口中即使没有保存 UNKNOWN，已消费 claim 的 recovery candidate 也阻断再次发送。

## 8. callbacks、accounting 与 reconciliation

继续由 RawCallbackWrapper 截取 openOrder、orderStatus、execDetails、commissionReport、error 和 disconnect。raw facts 不来自合成 Trade status；先入 durable inbox，后 normalize/lifecycle，再独立 account_pending。

重复 callbacks/execId 不重复 economic fill/accounting。foreign/manual order 无 durable owner 时不接管，事件保留并阻断。入库失败保存阻塞诊断并在当前 transport 保留未编码事件；不能编码的畸形原始 payload 不声称跨重启 durable。

Reconciliation 复用 3J 既有强身份比较和 durable evidence store。fresh query envelope 单独持久化，重复同事实查询不会破坏 readiness。MATCH 不修复 UNKNOWN、不生成 fills、不覆盖 cash/positions。LOCAL_ONLY/BROKER_ONLY/CONFLICT/UNKNOWN 和已有 failure 保守阻断；通用人工解除/清除 API 未实现。

## 9. cancel 与 SELL 行为

真实 Paper cancel 保持锁闭；既有 offline cancel lifecycle/adapter API 与不确定性语义保留。没有 synthetic cancel confirmation。

真实 Paper SELL 也保持锁闭。原因：3K 不做 broker positions 同步，本地 long inventory 无法证明 broker long inventory，不能用 SELL 意外开空。已有 broker-neutral BUY/SELL 映射保持兼容；真实 SELL 开放须等待 3L 的可信 broker inventory evidence。这是相对原始 BUY/SELL 提交目标的明确限制，不能宣称全部 3K 目标已无条件完成。

## 10. 测试覆盖与验证

新增 `tests/test_phase3k_paper_loop.py`：45 个参数化测试实例；生产 Paper transport/adapter/SQLite/registry/inbox 都是真实现，只 fake 外部 IB 调用。并发用 Barrier，deadline 用可控 monotonic，没有 sleep-based race 测试。

| 要求 | 证据 |
|---|---|
| 默认/无 opt-in 不发送 | 新 default/direct、double opt-in、manual harness gates；既有 read-only safety |
| wrong account / endpoint / generation / disconnect | 新 confirmation、endpoint mismatch、session/config mutation |
| qualification / mapping / preflight 不消费 claim/ID | 新 preparation failure tests；既有真实映射 prepare_order fault tests |
| 同 operation / 并发仅一次 / restart 不释放 | 新 success/restart、Barrier concurrency；既有 SQL/crash/subprocess tests |
| API 前 NOT_SENT / API 后 UNKNOWN | 新 ID/final preflight failures、timeout/disconnect、deadline |
| UNKNOWN 不重发 | 新 after-entry/deadline；既有 3J matched query does not clear UNKNOWN |
| callback/execId/accounting 去重 | 新 raw full loop/duplicate callbacks/harness；既有 commission gap/restart tests |
| foreign/manual 不接管 | 新 raw foreign order；既有 3J BROKER_ONLY |
| strong identity conflict | 既有 3J scenario D、ambiguous identity、persistent registry tests，全量继续通过 |
| pending callbacks / accounting / reconciliation / recovery 阻断 | 新 raw pending/reconciliation gates；既有 runner/3I pending accounting/recovery tests |
| config mutation / 无意外网络 | 新 frozen snapshot/mode/Live account tests；tests/conftest.py 真实 IO 禁用规则保持不变 |
| completion 定向审计不清除其他未知 | 新 post-fill audit/restart test；既有 true uncertainty regression tests |
| 无 broker inventory 不 SELL / 真实 cancel 锁 | 新 SELL/cancel tests |

最终完整 pytest、compile/import 和 git 证据见下方验证快照。

## 11. side effects、剩余能力与 Phase 3L

本轮没有连接真实 TWS，没有真实 Paper placeOrder/cancelOrder，没有 Live 操作。没有 commit、push、PR、merge、rebase、amend、reset、clean 或删除分支。所有变更保留在工作区，等待用户 review。

未实现：真实 SELL/cancel、通用人工恢复处置、broker NAV/cash/position sync、账户/组合 reconciliation、自动策略、scheduler、streaming、universe、Options、fractional、LIMIT/STOP、多账户、多进程协调、HA 或部署。Paper 类型核验仍依赖独立人工证据。

3L 建议：先定义 broker account/cash/position observation 和 provenance；对 local/broker 差异显式核对与审计，不用 NAV 覆盖 local cash。可信 broker long inventory 是真实 SELL 的前提；同时独立审查 cancellation 和 unresolved operator resolution。Strategy runtime/universe/configuration 留给 3M。

## 12. A–F 明确回答

A. 已具备真正 IBKR Paper order submission 的代码能力吗？**是，受控 BUY/MKT 路径会调用 IB.placeOrder；真实 SELL/cancel 暂锁闭，未在线验收。**

B. 默认状态仍无法意外下单吗？**是。** 默认 DISABLED，加显式双重 opt-in、当前账户/generation 人工确认和 durable 授权/claim/readiness。

C. 真正发送需用户手动解除 TWS Read-Only API 和程序侧双重 opt-in 吗？**是。** 程序不更改 TWS 设置；harness 另要求双环境 gate 和独立 SubmissionAuthorization。

D. 有进入 Live Trading 的受支持路径吗？**没有。** LIVE mode、Live port、非 DU identifier 拒绝；独立人工 Paper 核验的真实性仍是信任前提，不能声称获得了不可伪造的 broker 账户类型证明。

E. UNKNOWN 后有自动 resend 吗？**没有。** 永久 claim 与未决证据阻断，只有显式恢复核对。

F. 已是自动策略交易系统吗？**不是。** 这是首次受控 Paper side-effect foundation，不是自动 strategy runtime 或无人值守交易系统。

## 13. Final validation snapshot

- Full pytest after final fix and documentation: 637 passed / 0 failed / 1 skipped.
- Targeted Phase 3K: 46 passed / 0 failed.
- In-memory compile: 107 Python files; import smoke: 70 production modules; PASS.
- git diff --check: PASS.
- Baseline: 591 passed / 0 failed / 1 skipped.
- The only skip is the existing explicit read-only IBKR integration test.
- Regression: even a PaperNotSentError thrown after API entry is UNKNOWN, never NOT_SENT.

### git diff --stat (tracked changes only)

```text
 README.md                          | 18 ++++++---
 application/paper_runner.py        | 78 ++++++++++++++++++++++++++++++++++++++
 broker/ibkr/__init__.py            |  3 +-
 broker/ibkr/adapter.py             | 29 +++++++++++---
 broker/ibkr/config.py              |  2 +-
 broker/ibkr/events.py              |  3 +-
 docs/current_status.md             | 37 +++++++++---------
 docs/decisions.md                  | 14 +++++++
 docs/execution_recovery.md         |  8 ++++
 docs/ibkr_execution.md             |  8 ++++
 docs/ibkr_reconciliation.md        | 13 ++++++-
 docs/roadmap.md                    | 18 ++++++++-
 infrastructure/sqlite_execution.py | 21 ++++++++++
 13 files changed, 216 insertions(+), 36 deletions(-)
```

### git status --short

```text
 M README.md
 M application/paper_runner.py
 M broker/ibkr/__init__.py
 M broker/ibkr/adapter.py
 M broker/ibkr/config.py
 M broker/ibkr/events.py
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
?? tests/test_phase3k_paper_loop.py
```

### New test instances

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

46 tests collected in 0.17s
```

## 14. Pre-commit review follow-up

This document retains the original development validation snapshot (637 passed / 1 skipped, 46 new cases). The subsequent pre-commit review made minimal safety fixes: internal fresh-claim scope admission, exact BUY/request/spec validation, permanent generation retirement including connection-time callbacks, and durable unknown-diagnostic replay blocking. It added focused regression evidence, without unlocking SELL/cancel or adding account/position synchronization.

See [current Phase 3K Pre-Commit Review Report](phase3k_precommit_review_report.md) for severity, fixes, final test totals, Git evidence and verdict. The earlier tracked diff/stat/test instance snapshot is historical, not the post-review worktree.
