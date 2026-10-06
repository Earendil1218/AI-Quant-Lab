# Phase 3K — IBKR Paper Execution Loop Foundation

## 状态 / Status

Phase 3K 是首次受控 IBKR Paper side-effect capability，本地未提交、待 review；没有真实在线验收证据。起始 main 为 `bdf08e87804e0cc70a220e64b0dc97861f203dd3`（Phase 3J PR #11 merge）。

AI Quant Lab can perform an explicitly authorized, fail-closed, crash-aware IBKR Paper order execution loop. This is NOT automated trading, NOT strategy runtime, NOT Live Trading and NOT account/portfolio synchronization. Online Paper integration is opt-in only.

实际能力是受控单笔美股 BUY/MKT/DAY/integer quantity，经独立人工授权、持久化意图、Paper session 核验、真实 API boundary、raw callbacks、fill accounting 和 fresh reconciliation。broker-neutral BUY/SELL 映射继续保留，但真实 SELL 锁闭：本地 long inventory 不能证明 broker long inventory，开放前需要 Phase 3L 的可信账户/持仓证据。真实 cancel 同样锁闭。

The enabled real side effect is a single US equity BUY market order, not a background trading service. Supported account identifiers are additionally restricted to DU; that restriction is not a substitute for independent Paper verification. Existing neutral SELL and cancellation lifecycle APIs remain available to offline fakes. Real SELL and cancel fail closed.

## 组合与时序 / Composition and ordering

`PaperExecutionTransport` 复用 `ReadOnlyIBKRTransport` 的 owned IB、`RawCallbackWrapper`、session evidence、qualification、query 和事件队列；只读类本身没有解锁。构造不会连接。生产 adapter 必须使用同一数据库的 `SQLiteAttemptClaims` 和 `PersistentIdentityRegistry`，并有已持久化的 planning/risk/authorization。

```text
explicit connect opt-in + side-effect opt-in + current-session human Paper confirmation
  -> exact endpoint/account/generation validation
  -> startup fresh query + durable MATCH reconciliation
  -> consume pending raw callbacks
  -> plan and risk (local portfolio only)
  -> caller-created SubmissionAuthorization
  -> prepare and persist SUBMISSION_PENDING
  -> non-consuming validate
  -> qualification and order preparation
  -> locked current session/durable blocker preflight
  -> atomic permanent SQLite claim
  -> allocate IBKR ID and persist exact ownership
  -> verify current consumed snapshot and final preflight
  -> IB.placeOrder exactly once
  -> persist raw callbacks -> existing inbox/normalizer/lifecycle
  -> account_pending -> explicit fresh reconciliation
```

Transport lock serializes dispatch through one owned generation. SQL claims provide the durable one-winner operation boundary. Application planning, writes, ingestion and dispatch are still serialized by the caller; this is not multi-process coordination or HA. Qualification/mapping/preflight failure before the claim consumes neither claim nor broker ID. A post-claim failure never releases the claim, even when it is provably NOT_SENT.

## 人工授权与安全证据 / Human authority and safety evidence

以下条件必须同时成立，环境变量本身不能生成人工授权或发送权限：

- `PaperExecutionConfig.mode == PAPER`，`allow_side_effects is True`。
- 本地 host、7497、独立非零 client ID，单一独立核验账户 allowlist。
- 当前 session 实际 host/port/client ID 与构造时冻结快照一致；managed accounts 必须精确等于 `(expected_account,)`。
- `PaperSessionConfirmation` 绑定 exact account、当前 generation、明确 operator 及声明 `I verified this exact account is Simulated/Paper in TWS`。
- `connect_paper(..., integration_opt_in=True, side_effect_opt_in=True)` 两个调用参数必须显式为布尔 True。
- 同一数据库的已保存 planning ticket、risk decision、独立 `SubmissionAuthorization`、当前 pending snapshot、durable claim 和身份。
- 当前数据库已完成该会话的 startup reconciliation；无未决 observation、pending raw/inbox/accounting、阻塞 reconciliation 或需 review 的其他 recovery candidate。

**信任边界：IBKR Socket API 的现有 session evidence 不提供可用的账户类型证明。** Paper 配置和 allowlist 必须由用户独立确认，`PaperSessionConfirmation` 是人工部署证据，不是 broker 签发的 Paper 类型证明。端口、DU 前缀、client ID、readonly 参数均不能单独推断 Paper。代码不支持 LIVE mode/Live port，也不自动改 TWS 设置；不能宣称能识别虚假的人工 Paper 确认或任意被重新配置的 TWS endpoint。

Risk PASS ≠ human approval ≠ submission authority ≠ execution result. Neither the transport nor runner constructs a SubmissionAuthorization.

## 失败、回调与恢复 / Failure, callbacks and recovery

- ID 分配、身份持久化或发送前最后检查失败：可证明未进入 real API，返回 NOT_SENT；已领取 claim 永久保留，需 review。
- 一旦进入 `IB.placeOrder`，timeout/exception/同步断线一律 DELIVERY_UNKNOWN；runner 持久化 UNKNOWN。不使用返回的 Trade 合成状态作为 broker ack。
- 无 automatic reconnect、retry、resend；旧 generation 失效。新对象、新 runner、新 session 都不能释放旧 claim。
- `openOrder/orderStatus/execDetails/commissionReport/error/disconnect` 都沿用 raw wrapper。先将完整可编码 batch 写入 durable inbox，再 normalize/apply；不接管 foreign/manual order。
- 入库失败保留未入库事件在 transport，并持久化阻塞诊断。不能编码的畸形 callback 的原始内容仍在进程内保留；故障阻塞记录可跨重启保留，不声称该畸形 payload 已 durable。
- execId、经济 fill 和 accounting 使用既有幂等身份；broker Filled 本身从不增加经济数量。费用缺口由匹配的已接受 fill 定向解决。
- 若费用完整 fills 已把订单推进至 FILLED，确切 broker identity/request 匹配的历史 pending/held 和数量吻合的 completion hints 可审计标记 resolved；原 observation 保留。UNKNOWN、disconnect、数量冲突和其他未决证据不清除。
- reconciliation 只比较 execution/order/fill identity 与生命周期；MATCH 不修复 UNKNOWN、不修改现金或持仓、不授予新的订单权限。失败证据永久阻断，尚无通用人工解除 API。

## 人工在线验收入口 / Manual online acceptance entry

`application.paper_integration.run_authorized_paper_loop` 是显式 application 函数，不注册 CLI、scheduler、pytest 下单测试或自动启动入口。

运行前必须由用户自行完成：登录 TWS Simulated/Paper、确认确切账户、开启 Socket API/7497，并仅在正式授权验收时手动解除 TWS Read-Only API。程序不修改 TWS 设置。默认 pytest 继续禁止真实 IB/Client placeOrder/cancelOrder；既有 read-only integration opt-in 也不能使 pytest 下单。

手工调用还要求环境 gate：`RUN_IBKR_PAPER_INTEGRATION=1` 和 `ALLOW_IBKR_PAPER_ORDER_SIDE_EFFECTS=YES`，同时显式传入两个布尔 opt-in、当前 generation 的 `PaperSessionConfirmation` 和绑定确切最小 OrderRequest 的人工 `SubmissionAuthorization`。环境 flags 仅是附加 gate，不是授权。未提供则在连接前 fail closed。

显式组合示意（不自动制造人工确认或授权）：

```python
from broker.ibkr import (
    PaperExecutionTransport, IBKRPaperAdapter,
    PersistentIdentityRegistry, EquityContractSpec,
)
from infrastructure import SQLiteAttemptClaims
from application import PaperRunner
from application.paper_integration import run_authorized_paper_loop

transport = PaperExecutionTransport(config)
adapter = IBKRPaperAdapter(config, EquityContractSpec(instrument), transport,
                          SQLiteAttemptClaims(repository),
                          PersistentIdentityRegistry(repository, transport.generation))
runner = PaperRunner(repository, adapter)
# operator_confirmation must name transport.generation and the independently
# verified exact Paper account. human_authorization is supplied by the user.
result = run_authorized_paper_loop(
    runner, confirmation=operator_confirmation,
    intent=explicit_intent, sizing=explicit_sizing,
    risk_configuration=explicit_risk, valuation=explicit_valuation,
    authorization=human_authorization,
    integration_opt_in=True, side_effect_opt_in=True,
)
```

Harness 有界等待（默认 30 秒、最大 60 秒）只消费该笔订单 callback，不是 strategy/market-data loop。若达到 deadline 仍无法确认终态，则保存 UNKNOWN 并返回需要 review 的结果；绝不重发或自动撤单。费用完整终态后做 fresh reconciliation，并关闭 owned session。用户仍应在 TWS Orders/Trades 人工核对。开发过程中未执行真实在线入口。

## 延后 / Deferred

Phase 3L：独立 broker cash/NAV/positions 观察与 provenance、local/broker 差异核对；禁止无审计覆盖 local cash。可信 broker inventory 是开放真实 SELL 的前提。需另行审查真实 cancellation 和未决证据人工处置。

Phase 3M：strategy runtime、universe、trading configuration；3K 不包含 scheduler、streaming market data、自动选股或自动触发订单。无 options、fractional、LIMIT/STOP、bracket、multi-leg、futures、forex、Live Trading、多账户、部署或 HA。

## Pre-commit safety audit / 提交前安全审查

发送 scope 已改为内部 `_dispatch_scope`，入口验证尚未消费的 durable claim，避免用已消费 claim 重入并绕过 adapter；公开 `place/next_order_id` 没有内部 scope 时仍拒绝。边界使用确切 OrderSide.BUY，并重新核对获授权 instrument 与 spec。连接期 disconnect、connectivity/recovery notice 或未知诊断永久退役该 generation，连接返回不得恢复权限。

未知 broker diagnostic 在 durable inbox replay 阶段保存 review-required blocker，所以即使在 raw commit 后、normalization 前崩溃，重启重放也不会因无订单关联而清除阻塞。信息类通知不会伪造未知状态。所有发送与重放仍是人工显式编排，没有 retry、SELL、cancel 或新功能。

Paper-only evidence remains operator-dependent; there is no cryptographically authoritative broker account type proof. Private IB objects/internal state are trusted application internals, not a security sandbox against arbitrary Python mutation. The library connection bootstrap may cache account/position responses in its own IB object; Phase 3K never consumes them as local cash/NAV/position truth or synchronizes them into local accounting.

Review evidence and verdict: [Phase 3K Pre-Commit Review Report](phase3k_precommit_review_report.md).
