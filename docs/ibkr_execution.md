# Phase 3H — IBKR Paper Execution Adapter Foundation

## 范围 / Scope

中文：本阶段建立离线可验证的 execution boundary，不是 Paper runner。`trading.Fill`、回测、risk、portfolio 和 strategy 保持隔离。真实 `ReadOnlyIBKRTransport.place/cancel` **始终拒绝**，即使配置 opt-in；目前只有 fake transport 可以验证发送边界。内存 repository/claim 没有 crash durability，账户 API 也不提供本项目可依赖的统一 Paper 证明，因此不能宣称 unattended、restart-safe 或 Live-ready。

English: This foundation establishes an offline-verifiable execution boundary, not a Paper runner. Trading economics, backtest, risk, portfolio and strategy remain isolated. Real `ReadOnlyIBKRTransport.place/cancel` **always reject**, even with opt-in. Fake transports exercise dispatch. Memory stores are not crash-durable, and this project has no universal API-backed proof of Paper account type. This is not unattended, restart-safe or Live-ready execution.

## 架构 / Architecture

```text
Caller: authorization → begin_submission → repository.save
  → IBKRPaperAdapter → prepare → revalidate → atomic claim → identity registration → transport
  ← raw callback snapshots → IBKREventNormalizer → ExecutionObservation
  → apply_execution_observation → repository.save → optional accounting

execution/ → trading/ and existing risk contracts
broker/ibkr/ → execution/ + trading/ + ib_insync 0.9.86
backtest/ does not depend on broker/ibkr/
```

中文：调用方拥有 repository、claims、registry、normalizer 和 session 的生命周期。同一执行范围的多个 adapter 必须共享同一个 claim 实例和 identity registry。claim 锁保证并发领取至多一次，不是 repository 与外部调用的事务；调用方还必须串行化状态写入与 dispatch。没有全局可变 broker、后台 consumer 或自动事件循环。归一化错误必须显式处理，不可吞掉后继续交易。

English: The caller owns repositories, claims, identity registries, normalizers and sessions. Adapters in one execution scope must share the same claim instance and identity registry. The claim lock guarantees one concurrent claimant; it is not a repository/network transaction. Callers must serialize state writes with dispatch. There is no mutable global broker, background consumer or automatic runner. Normalization failures must be handled explicitly and must block further trading.

## 提交与幂等 / Submission and idempotency

中文：risk APPROVED 不等于 SubmissionAuthorization。先非消费验证授权、pending state 和完整保存快照，再完成合约映射、qualification、订单映射与 Paper/session preflight。准备不分配 broker order ID。随后在 claim 锁内重读完整快照并按 `(ClientOrderId, operation)` 原子消费；准备期间快照改变返回 NOT_SENT，不消费 claim。只有获胜者分配身份、注册并进入 transport。准备失败修正后可再次显式调用，因为从未消费 claim；没有自动 retry 或 release。进入 transport 后的异常成为 DELIVERY_UNKNOWN，保留原异常类型及消息，claim 永不释放。

English: Risk APPROVED is not SubmissionAuthorization. Non-consuming validation of authority, pending state and the complete saved snapshot precedes mapping, qualification and Paper/session preflight. Preparation allocates no broker order ID. The claim lock then rechecks the full snapshot and atomically consumes `(ClientOrderId, operation)`; stale preparation returns NOT_SENT without claiming. Only the winner allocates/registers identity and enters transport. Corrected preparation permits another explicit call because no claim was consumed; there is no automatic retry or release. Exceptions after transport entry become DELIVERY_UNKNOWN with original type/message; consumed claims are never released.

| Result | 中文 | English |
|---|---|---|
| NOT_SENT | 能证明未进入发送入口 | Proven not to have entered send |
| DISPATCH_RETURNED | API 返回，不推进 SUBMITTED/ACKNOWLEDGED | API returned, without lifecycle acceptance |
| DELIVERY_UNKNOWN | 可能送达，应用为 UNKNOWN，禁止重试 | May have arrived; apply UNKNOWN, never retry |

中文：进程退出会失去 claim。新建 claim 对象不是恢复方案。生产持久化、恢复、跨进程协调必须在 Phase 3I 单独设计；本阶段真实订单因此保持锁闭。没有 SQLite、journal、lease、heartbeat、retry queue。

English: Claims disappear with the process. Constructing a fresh claim store is not recovery. Production persistence, recovery and cross-process coordination belong to Phase 3I; real orders therefore remain locked. No SQLite, journal, lease, heartbeat or retry queue is implemented.

## Mapping 与身份 / Mapping and identity

中文：显式 `EquityContractSpec` 只允许一个 equity；domain 没有国家/币种字段，不能把任意 symbol 自动当作美股。映射 STK/SMART/USD，必要时指定 primary exchange，qualification 必须返回唯一且一致的正 conId 合约。OrderRequest 只接受当前精确类型，BUY/SELL 整股映射 MKT/DAY、常规时段。没有 limit、options、fractional、short-selling 或 margin 模型。SELL 本身不是 long-only 证明，未来 runner 仍需可靠持仓与未完成订单控制。

English: An explicit EquityContractSpec allows one equity. Since the domain has no country/currency fields, arbitrary symbols are not assumed to be US stocks. Mapping uses STK/SMART/USD with optional primary exchange; qualification must return exactly one matching positive-conId contract. Only the current exact OrderRequest type is accepted, mapping integer BUY/SELL shares to MKT/DAY in regular hours. There are no advanced orders, options, fractional, short-selling or margin models. SELL is not proof of long-only safety; a future runner needs reliable positions and outstanding-order controls.

| Identity | 中文 | English |
|---|---|---|
| ClientOrderId | 本地稳定逻辑订单 | Stable local logical order |
| clientId + orderId + generation | API ownership，限制当前连接 | API ownership limited to the session |
| account + permId | 正 permId 才绑定 BrokerOrderId；0 为未知 | Positive permId binds BrokerOrderId; zero remains unknown |
| account + 完整 execId | BrokerExecutionId；UUIDv5 派生 ExecutionFillId | BrokerExecutionId; UUIDv5 derives ExecutionFillId |

中文：正向/反向索引均唯一，冲突失败。orderRef 仅用于请求关联，不是 broker 幂等键。status 无 account 字段时只能从已注册 session 映射取得账户；openOrder 和 execution 必须验证实际账户和经济字段。旧 generation、外来 API ID 不能自动认领。

English: Forward and reverse bindings are unique and conflicts fail. orderRef provides correlation, not broker idempotency. Status callbacks lacking account fields rely only on registered session mappings; openOrder/execution validate actual accounts and economics. Stale generations and foreign API identities cannot be adopted automatically.

## 原始事件 / Raw events

中文：`RawCallbackWrapper` 在 0.9.86 decoder 调用的 wrapper 方法入口复制不可变快照，之后才调用原库处理。高层 Trade/statusEvent 不作为 broker truth，因为 `cancelOrder` 与 `Wrapper.error` 可以在本地合成 PendingCancel/Cancelled。原始 error payload（包括 advanced rejection JSON）保留在 queue，调用方 `read_events()` 后负责保留诊断。归一化为显式观察，不修改 aggregate。

English: RawCallbackWrapper copies immutable snapshots at the 0.9.86 decoder-to-wrapper boundary before library processing. High-level Trade/statusEvent is not broker truth: cancelOrder and Wrapper.error can synthesize local PendingCancel/Cancelled states. Raw errors, including advanced rejection JSON, are queued; callers own diagnostic retention after read_events(). Normalization emits facts without mutating aggregates.

中文：PendingSubmit/PreSubmitted/Inactive/未知 status 保留为 pending/held/unresolved。Submitted 允许有身份校验的 acknowledgement；连接丢失使在途订单 UNKNOWN，不回退已完成经济事实。状态 callback 不保证完整或有序。没有可信身份的事实不能确认订单。

English: PendingSubmit/PreSubmitted/Inactive/unknown statuses remain pending/held/unresolved facts. Submitted permits identity-validated acknowledgement. Connection loss moves in-flight orders to UNKNOWN without undoing terminal economics. Status callbacks need not be complete or ordered. Facts lacking trusted identity cannot acknowledge an order.

## 成交、佣金与时间 / Fills, commission and time

中文：broker Filled 只输出 COMPLETION；`ObservationApplication.unresolved=True` 表示 broker completion 已观察到而经济明细尚未解决。绝不因此生成 Fill 或增加 cumulative quantity。execution 和真实 CommissionReport 按 execId 配对后，才创建 immutable ExecutionFill。raw execution 的 placeholder commission 不使用。明确零费用允许；未知、UNSET_DOUBLE、负值、非 USD 费用失败，不静默转零或换汇。

English: Broker Filled emits COMPLETION only. ObservationApplication.unresolved=True exposes observed completion with unresolved economics; it never creates fills or increments cumulative quantity. Executions are paired with actual CommissionReport callbacks by execId before creating immutable ExecutionFill. Placeholder fees are ignored. Explicit zero is valid; missing, UNSET_DOUBLE, negative or non-USD costs fail without silent defaults or currency conversion.

中文：经济 filled_at 使用 execution_time；observed_at 是本地接收时间；applied_at 是调用方单调应用时间，不允许早于接收时间或订单 updated_at。配对支持先后到达及重复；完整相同 ID/内容幂等，不同内容冲突。由 `record_fill()` 唯一累计数量并防止 overfill，status 数量只用于核对。识别到 execution correction family 或佣金修正时失败，账务冲正留待后续设计。

English: Economic filled_at uses execution_time; observed_at is local receipt time; applied_at is a monotonic caller application time no earlier than receipt or order updated_at. Pairing handles either arrival order and replay. Identical identities/content are idempotent; differing content conflicts. Only record_fill() accumulates economic quantity and prevents overfill; status quantities are comparisons only. Execution correction families and commission revisions fail pending future adjustment-accounting design.

中文：旧 `apply_broker_order_observation()` 保持参数和 ExecutionOrder 返回类型，但 broker quantity 仅用于比较，不再写入经济累计。UNKNOWN 收到成交状态快照时，只有本地累计与已接受 fills 总量均匹配快照才确认生命周期；缺失明细时保持 UNKNOWN，调用方用 `reconcile_order()` 获取数量差异。快照先到不妨碍后续真实 ExecutionFill；重放快照不重复累计。历史不一致 aggregate 的 record_fill 防护仍保留。新 adapter 使用 ExecutionObservation；调用方先保存再考虑会计，fill_accepted 不提供跨 repository/portfolio 原子事务。

English: Legacy apply_broker_order_observation() retains its arguments and ExecutionOrder return type, but broker quantity is comparison evidence and never writes economic totals. Fill-state snapshots resolve UNKNOWN only when local cumulative quantity and accepted fill totals both match. Missing evidence stays UNKNOWN; reconcile_order() reports quantity issues. An earlier snapshot does not block later ExecutionFill acceptance, and snapshot replay never adds quantity. The record_fill guard against historically inconsistent aggregates remains. The new adapter uses ExecutionObservation; callers save before accounting, and fill_accepted provides no repository/portfolio atomic transaction.

中文：unresolved 是本次 observation 的结果，不是持久化 readiness latch。后续一笔 partial fill 返回 false 不会自动解决先前 broker completion 的缺失明细；调用方必须保留待解决观察并核对全部经济明细，本阶段不提供自动清除或 runner。

English: unresolved describes one observation, not a persistent readiness latch. A later partial fill returning false does not automatically resolve missing details from earlier broker completion. Callers must retain outstanding observations and verify all economics; this phase has no automatic clearing or runner.

## 撤单竞态 / Cancellation races

中文：CANCELLED 表示剩余未成交部分已取消，并不意味着该订单从未成交。UNKNOWN 表示未解决的生命周期结果，不删除已接受成交、BrokerExecutionId、BrokerOrderId、请求或授权。

English: CANCELLED means the remaining unfilled quantity was cancelled; it does not imply zero fills. UNKNOWN describes unresolved lifecycle outcome and preserves accepted fills, execution/order identities, request and authorization.

中文：CANCEL_PENDING 期间 partial fill 保持撤单意图；全成交进入 FILLED。取消确认保留已成交数量。CANCELLED 后的迟到 execution 必须携带既有匹配 broker identity，仍经 record_fill 去重和数量校验，部分成交保持 CANCELLED，全成交进入 FILLED。REJECTED 后成交不自动改写拒单，要求人工 reconciliation。不会放开任意状态跳转。

English: Partial fills during CANCEL_PENDING retain cancellation intent; full fills become FILLED. Cancellation keeps recorded fills. Late execution after CANCELLED requires the existing matching broker identity and still passes deduplication/quantity checks. Partial late fills remain CANCELLED; full late fills become FILLED. Fills conflicting with REJECTED require manual reconciliation. There is no unrestricted state-transition bypass.

## 安全与验证 / Safety and verification

中文：配置默认 DISABLED；显式 PAPER、副作用 opt-in、独立非零 client ID、单一预核验账户 allowlist、managed accounts 精确匹配、有效 generation、authorization、保存快照和 claim 均是必要条件。7497/DU 前缀/readonly 参数都不能单独证明安全。即使这些满足，真实 transport 仍锁闭，避免把内存保护误称为可上线交易。

English: Configuration defaults to DISABLED. Explicit PAPER mode, side-effect opt-in, a dedicated nonzero client ID, one independently verified account allowlist, exact managed-account match, valid generation, authorization, saved snapshot and claim are necessary conditions. Port 7497, DU prefixes and readonly arguments are not sufficient proof. Even when these pass, real transport remains locked; memory safeguards are not deployment readiness.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.venv311\Scripts\python.exe -m pytest -p no:cacheprovider -v
```

中文：默认 fixture 拦截真实网络、IB/Client connect/placeOrder/cancelOrder；即使被测代码吞掉拦截异常，teardown 仍失败。只有 `RUN_IBKR_PAPER_INTEGRATION=1` 才可运行只读 integration；该测试仍禁止订单入口。本阶段验收不运行在线测试。

English: Default fixtures block network and real IB/Client connect/placeOrder/cancelOrder. Teardown fails even if tested code catches a blocked call. Only RUN_IBKR_PAPER_INTEGRATION=1 enables the read-only integration test, which still blocks order methods. Phase 3H acceptance does not run online tests.

## 后续与依据 / Deferred work and references

中文：Phase 3I — Paper Trading Runner & Recovery Foundation 才考虑生产持久化、restart recovery、显式人工审批 workflow、Paper runner、未完成订单感知 planning、周期/组合 reconciliation、audit trail、monitoring 与 alerts。自动重试必须先解决重复订单风险；Live Trading、期权执行仍是独立后续范围。

English: Phase 3I — Paper Trading Runner & Recovery Foundation considers production persistence, restart recovery, explicit approval workflow, a Paper runner, outstanding-order-aware planning, periodic/portfolio reconciliation, audit trails, monitoring and alerts. Automatic retry requires duplicate-order safety first. Live Trading and options execution remain separate future scope.

Transport contract: local ib-insync 0.9.86 source (`ib.py`, `wrapper.py`), pinned in requirements. 中文：新版 API 的 CommissionAndFeesReport 不用于本版模型；迁移需重新验证。 English: New CommissionAndFeesReport APIs are not substituted into this version; migration requires revalidation.

- [IBKR order identities and statuses](https://interactivebrokers.github.io/tws-api/order_submission.html)
- [IBKR executions, commissions and corrections](https://interactivebrokers.github.io/tws-api/executions_commissions.html)
- [IBKR error codes](https://interactivebrokers.github.io/tws-api/message_codes.html)
- [ib-insync 0.9.86 source](https://ib-insync.readthedocs.io/_modules/ib_insync/ib.html)

中文：上述旧 TWS 文档用于核对固定版本语义，不代表对最新 TWS 全版本兼容的声明。
English: Historical TWS references support the pinned contract, not a claim of compatibility with every current TWS version.
