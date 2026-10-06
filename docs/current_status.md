# 当前项目状态 / Current Project Status

最后更新 / Last updated: 2026-10-06

## 当前里程碑 / Current Milestone

### 中文

- 版本：AI Quant Lab v0.10
- Roadmap：Phase 3I — Paper Trading Runner & Recovery Foundation（本地实现，未提交，待 review）
- 基线状态：Phase 3H completed and merged，implementation `d73308d`，PR #9 merge `6319e98`；v0.10。下一阶段为 Phase 3I；在线只读 integration 尚无正式验收证据，真实订单 transport 仍 fail-closed。

### English

- Version: AI Quant Lab v0.10
- Roadmap: Phase 3I — Paper Trading Runner & Recovery Foundation (implemented locally, uncommitted, awaiting review)
- Baseline: Phase 3H completed and merged, implementation `d73308d`, PR #9 merge `6319e98`; v0.10. Phase 3I follows. Online read-only integration has no formal acceptance evidence; real order transport remains fail-closed.

## 已完成 / Completed

### 中文

- 保留 IBKR TWS Paper Trading `readonly=True` 历史数据链路。
- 新增独立 `data.processing` 模块，标准化 schema、datetime、OHLCV dtype、时间顺序和 index。
- processed 数据固定为 `date, open, high, low, close, volume`。
- 重复时间戳明确报错，不静默保留 first 或 last。
- validation 增加 volume、有限数值、负价格和负成交量规则。
- 正式启用 `data/processed/SYMBOL_INTERVAL.csv`。
- `main.py` 形成 raw validation、raw storage、processing、processed validation、processed storage 和 reload verification 的完整流程。
- README 建立中英双语开源入口并增加 Project Origin。
- 建立渐进式双语文档、docstring 和重要注释规范。
- Phase 3B 已合并到 `main`，提供 simple/log/cumulative return 和基础统计。
- Phase 3C 提供日期化收益、多资产精确日期对齐、财富与回撤、完整窗口滚动收益和波动率、benchmark 比较、active return、tracking error 与统一样本 Pearson correlation。
- Phase 3D 提供 trailing moving average、显式 signal state、Strategy abstraction 和 long/flat target-position intent。
- Phase 3E 提供 broker-neutral trading domain、fixed-quantity sizing、portfolio accounting 和 next-open deterministic backtest vertical slice。
- Phase 3F 提供 broker-neutral risk configuration、valuation context、deterministic risk decisions，以及 allowed-instrument、quantity、resulting-position 和 equity-notional checks。
- Phase 3G 提供 broker-neutral execution identities、显式 submission authorization、immutable lifecycle、optimistic repository contract、partial-fill deduplication 和 reconciliation-friendly observations。

### English

- Preserved the read-only IBKR TWS Paper Trading historical-data boundary.
- Added `data.processing` for schema, datetime, OHLCV dtype, chronological order, and index normalization.
- Defined the processed schema as `date, open, high, low, close, volume`.
- Made duplicate timestamps an explicit error instead of silently keeping the first or last row.
- Extended validation to cover volume, finite values, negative prices, and negative volume.
- Activated `data/processed/SYMBOL_INTERVAL.csv` as the processed-data layer.
- Extended `main.py` across raw validation and storage, processing, processed validation and storage, and reload verification.
- Established a bilingual README entry point with a Project Origin section.
- Established progressive bilingual conventions for documentation, docstrings, and important comments.
- Phase 3B is merged into `main` and provides simple, log, and cumulative returns plus basic statistics.
- Phase 3C provides date-aware returns, exact-date multi-asset alignment, wealth and drawdown analysis, complete-window rolling returns and volatility, benchmark comparison, active returns, tracking error, and shared-sample Pearson correlation.
- Phase 3D provides trailing moving averages, explicit signal states, a Strategy abstraction, and long/flat target-position intent.
- Phase 3E provides a broker-neutral trading domain, fixed-quantity sizing, portfolio accounting, and a deterministic next-open backtest vertical slice.
- Phase 3F provides broker-neutral risk configuration, valuation context, deterministic risk decisions, and allowed-instrument, quantity, resulting-position, and equity-notional checks.
- Phase 3G provides broker-neutral execution identities, explicit submission authorization, an immutable lifecycle, an optimistic repository contract, partial-fill deduplication, and reconciliation-friendly observations.

## 已验证 / Verified

### 中文

- Phase 3H 基线为 449 passed / 1 skipped；Phase 3I 全量离线测试为 537 passed / 0 failed / 1 skipped，较 3H 新增 88 项（本轮安全修复新增 35 项）。只读 integration 仍 opt-in，本轮未运行在线验证。
- processing、validation、raw/processed path 和 CSV round-trip 均由固定输入或 pytest 临时目录验证。
- 测试不连接真实 TWS，不写入项目数据目录，也不调用订单接口。
- Phase 2 曾由用户人工在线验证：成功获取、验证、保存并重载 251 条 NVDA 日线数据。
- Phase 3A 于 2026-08-19 由用户人工在线验证：251 条 NVDA 日线完成 raw 保存、processed 保存、重载验证并正常断开 TWS。

### English

- Phase 3H baseline: 449 passed / 1 skipped. Phase 3I full offline suite: 537 passed / 0 failed / 1 skipped, adding 88 cases since 3H (35 safety-fix cases this round). Read-only integration remains opt-in; no online verification was performed.
- Processing, validation, raw/processed paths, and CSV round trips use deterministic inputs or pytest temporary directories.
- Tests do not connect to TWS, write to project data directories, or invoke order APIs.
- Phase 2 was previously verified manually online with 251 NVDA daily bars fetched, validated, saved, and reloaded.
- Phase 3A was manually verified online on 2026-08-19: 251 NVDA daily bars completed raw storage, processed storage, reload validation, and a clean TWS disconnect.

## Phase 3C / Performance and Comparative Research Foundation

### 中文

- 日期化收益使用无时区、唯一且升序的 `DatetimeIndex`；leading NaN 表示首日没有可定义收益。
- 多资产与 benchmark 使用精确共同日期交集，不填充缺失收益。
- 支持 wealth index、drawdown series、maximum drawdown 及 peak/trough/recovery 日期。
- 支持完整窗口 rolling compounded return 和 `ddof=1` rolling annualized volatility。
- 支持 active return、共同起点累计表现、annualized tracking error 和统一共同样本 Pearson correlation matrix。
- Research 保持纯内存计算，与 broker、storage、strategy、backtest 和 portfolio 解耦。

### English

- Date-aware returns use a timezone-naive, unique, ascending `DatetimeIndex`; the leading NaN means the first date has no defined return.
- Assets and benchmarks use their exact common-date intersection without filling missing returns.
- Wealth index, drawdown series, maximum drawdown, and peak/trough/recovery dates are supported.
- Complete-window rolling compounded return and `ddof=1` rolling annualized volatility are supported.
- Active returns, common-start cumulative performance, annualized tracking error, and a shared-sample Pearson correlation matrix are supported.
- Research remains pure in-memory calculation, decoupled from broker, storage, strategy, backtest, and portfolio layers.

## Phase 3D / Signal and Strategy Foundation

- `research.calculate_moving_average` 使用 trailing complete windows，只计算截至当日的观察。
- Signal 输出显式携带 `signal_type`、MA 数值、state 和 numeric value。
- Strategy intent 输出 `signal_type`、`signal_state` 和 float64 `target_position`。
- warm-up 为 `unavailable` / `NaN`；`1.0` 表示 long，`0.0` 表示 flat。
- MA crossover strategy 是冻结配置的纯内存 reference implementation，不连接 broker 或 execution。
- future mutation 与 future append 测试锁定历史输出不变的 look-ahead policy。

- `research.calculate_moving_average` uses trailing complete windows and observations available through each date only.
- Signals explicitly carry a `signal_type`, MA values, state, and numeric value.
- Strategy intent outputs `signal_type`, `signal_state`, and a float64 `target_position`.
- Warm-up is `unavailable` / `NaN`; `1.0` means long and `0.0` means flat.
- The MA crossover is a frozen-configuration, in-memory reference implementation with no broker or execution access.
- Future-mutation and future-append tests lock the no-look-ahead policy.

## Phase 3E / Trading Domain and Backtest Foundation

- `target_position` 在 trading boundary 中解释为 standardized target exposure；它不代表 shares、NAV、notional 或固定金额。
- `FixedQuantitySizing` 独立地将 long/flat exposure 转换为 target quantity，再由 portfolio reconciliation 生成 order plan。
- `trading` 提供 broker-neutral instrument、intent、order、fill 和 rejection records，不依赖 pandas 或 ib_insync。
- `PortfolioState` 只通过 Fill 更新 cash 与 position quantity；本阶段不引入未定义的 average-cost accounting。
- planning decision 与 execution rejection 使用不同 enum；当前执行拒绝包括 insufficient cash 和 no next bar。
- daily lifecycle 固定为 OPEN 执行 pending order，CLOSE mark/snapshot/observe/plan；禁止 same-close fill。
- accounting boundary 使用 Decimal；research/OHLCV 保持 float64，equity curve 明确提供 float64 pandas view。

- At the trading boundary, `target_position` means standardized target exposure; it is not shares, NAV, notional, or a fixed currency amount.
- `FixedQuantitySizing` independently converts long/flat exposure into target quantity before portfolio reconciliation creates an order plan.
- `trading` provides broker-neutral instrument, intent, order, fill, and rejection records without pandas or ib_insync dependencies.
- `PortfolioState` updates cash and position quantity only through Fill; undefined average-cost accounting is intentionally absent.
- Planning decisions and execution rejections use separate enums; current execution rejections cover insufficient cash and no next bar.
- The daily lifecycle executes pending orders at OPEN, then marks/snapshots/observes/plans at CLOSE; same-close fills are prohibited.
- Accounting uses Decimal while research/OHLCV remains float64; the equity curve is an explicit float64 pandas view.

## Phase 3F / Pre-Trade Risk and Execution Handoff Foundation

- `RiskConfiguration` 只启用显式配置的规则；`BacktestEngine.risk_configuration=None` 表示 risk layer disabled，而不是隐式宽松批准。
- `evaluate_order_risk` 一旦调用即 fail closed，固定顺序检查 allowed instrument、order quantity、long-only resulting position、position quantity 和 equity order notional。
- BUY resulting quantity 为 current + order；SELL 为 current - order；负结果使用 `SHORT_POSITION_NOT_ALLOWED` 在 risk boundary 拒绝。
- `allowed_instruments=None` 表示规则 disabled；empty `frozenset` 表示不允许任何 instrument；只接受 `InstrumentId`。
- Backtest 在真正到达 T+1 OPEN 时、simulation 前评估风险；notional 使用该 OPEN 的 `Decimal(str(price))` valuation。
- 最后一根 bar 的 pending order 没有 risk horizon，直接产生 `NO_NEXT_BAR`；因此 orders 数量不一定等于 risk decisions 数量。
- `RiskDecision.evaluated_at` 来自 `ValuationContext.observed_at`，不读取 wall clock。
- Risk approval 不修改 portfolio、不创建 Fill，也不表示人工批准、提交授权或 broker acknowledgement。

- `RiskConfiguration` enables only explicit rules; `BacktestEngine.risk_configuration=None` means the risk layer is disabled rather than implicitly approved by a permissive configuration.
- Once called, `evaluate_order_risk` is fail-closed and checks allowed instrument, order quantity, long-only resulting position, position quantity, and equity order notional in a fixed order.
- BUY resulting quantity is current + order; SELL is current - order; a negative result is rejected at the risk boundary with `SHORT_POSITION_NOT_ALLOWED`.
- `allowed_instruments=None` disables that rule; an empty `frozenset` allows no instruments; only `InstrumentId` values are accepted.
- Backtests evaluate risk only at an available T+1 OPEN before simulation; notional uses that OPEN converted through `Decimal(str(price))`.
- A final-bar pending order has no risk horizon and receives `NO_NEXT_BAR` directly, so order and risk-decision counts need not match.
- `RiskDecision.evaluated_at` comes from `ValuationContext.observed_at`, never the wall clock.
- Risk approval neither mutates the portfolio nor creates a Fill, and it grants no human or broker-submission authority.

## Phase 3G / Broker-Neutral Execution Lifecycle Foundation

- 独立 `execution` package 定义系统生成的 `ClientOrderId`，并将 `BrokerOrderId`、`BrokerExecutionId` 和 `ExecutionFillId` 保持为不同身份。
- `SubmissionAuthorization` 显式绑定 client order、完整 request、时间和 audit authority；只有匹配的 approved `RiskDecision` 才能使 execution order 进入 `AUTHORIZED`。
- immutable `ExecutionOrder` 和纯 lifecycle functions 覆盖 CREATED、AUTHORIZED、SUBMISSION_PENDING、SUBMITTED、ACKNOWLEDGED、PARTIALLY_FILLED、FILLED、CANCEL_PENDING、CANCELLED、REJECTED 和 UNKNOWN。
- `AUTHORIZED → SUBMISSION_PENDING` 建立 durable-intent-before-side-effect contract；UNKNOWN 禁止重复 begin submission，只能通过 reconciliation 或人工处置收敛。
- repository protocol 提供 add/get/optimistic save；in-memory implementation 明确不提供 crash/restart durability。
- `ExecutionFill` 关联 unchanged economic `Fill`，支持 multiple fills、overfill protection、fill identity deduplication 和 cancel race 中的 late fills。
- broker-neutral observations 和 reconciliation results 不执行 broker I/O、polling 或 portfolio-position reconciliation。

- The independent `execution` package defines system-generated `ClientOrderId` values while keeping broker order, broker execution, and execution-fill identities separate.
- `SubmissionAuthorization` explicitly binds the client order, complete request, timestamp, and audit authority; only a matching approved `RiskDecision` can move an execution order to `AUTHORIZED`.
- The immutable aggregate and pure lifecycle functions cover CREATED, AUTHORIZED, SUBMISSION_PENDING, SUBMITTED, ACKNOWLEDGED, PARTIALLY_FILLED, FILLED, CANCEL_PENDING, CANCELLED, REJECTED, and UNKNOWN.
- `AUTHORIZED → SUBMISSION_PENDING` establishes the durable-intent-before-side-effect contract. UNKNOWN blocks resubmission until reconciliation or manual resolution.
- The repository protocol provides add/get/optimistic-save semantics; its in-memory implementation explicitly provides no crash or restart durability.
- `ExecutionFill` associates provenance with the unchanged economic `Fill` and supports multiple fills, overfill protection, identity deduplication, and late fills during cancellation.
- Broker-neutral observations and reconciliation results perform no broker I/O, polling, or portfolio-position reconciliation.

## 已知限制 / Known Limitations

### 中文

- 当前仅正式支持 `1 day → 1d` 文件名映射。
- CSV 保存仍是同名文件全量覆盖，尚未实现增量合并。
- 日线 date 必须不含时区；分钟线和多时区策略尚未设计。
- 尚未处理拆股、分红或 adjusted price。
- 尚未设计多交易所 calendar policy。
- 当前 backtest 仅支持 single-equity、daily、long/flat、fixed quantity、next-open execution；尚未实现 Options、Greeks 或 advanced portfolio risk。
- 不支持自动化 Paper Trading 或 Live Trading。
- IBKR adapter 真实订单 transport 仍锁闭。3I 提供 SQLite repository/claim、显式恢复、成交重放与最小离线 runner；未完成订单会阻止新规划，但不提供净额调整或完整 outstanding-order-aware planning。human approval workflow、automatic retry、broker/local portfolio reconciliation、monitoring、alerts 和 OMS 未实现。
- fake 已覆盖连接、qualification 和错误边界；Phase 3H 尚未进行在线验证。

### English

- Only the `1 day → 1d` filename mapping is formally supported.
- CSV persistence still replaces the complete file; incremental merging is not implemented.
- Daily dates must be timezone-naive; intraday and multi-timezone policies are not yet designed.
- Splits, dividends, and adjusted prices are not handled.
- No multi-exchange calendar policy has been designed.
- Backtesting is limited to single-equity, daily, long/flat, fixed-quantity, next-open execution; options, Greeks, and advanced portfolio risk are not implemented.
- Automated paper trading and live trading are not supported.
- Real order transport remains locked. Phase 3I provides SQLite repositories/claims, explicit recovery, fill replay and a minimal offline runner. Outstanding executions block new planning; there is no netting or full outstanding-order-aware planner. Approval workflows, automatic retry, broker/local portfolio reconciliation, monitoring, alerts and an OMS are not implemented.
- Fake transport covers connection, qualification and error boundaries; Phase 3H has not been verified online.

## Phase 3H / IBKR Paper Execution Adapter Foundation

中文：Pre-Commit 最小修复已完成：prepare → revalidate → claim → side effect，准备失败不消费 claim；旧 reconciliation quantity 仅作证据，经济累计只接受 ExecutionFill。UNKNOWN 保留已知事实；CANCELLED 表示剩余未成交部分取消，不意味着从未成交。已固化部分成交后 UNKNOWN、取消后迟到成交和重复佣金的精确回归。

English: Pre-commit minimal fixes implement prepare → revalidate → claim → side effect without consuming claims on preparation failure. Legacy reconciliation quantities are evidence only; accepted ExecutionFill records alone advance economics. UNKNOWN preserves facts; CANCELLED cancels the remaining quantity and does not imply zero fills. Exact regressions cover UNKNOWN after partial execution, late cancelled fills and commission replay.

中文：已实现 broker/ibkr 映射、独立身份、提交/撤单边界、原始回调归一化、错误分类、execution/commission 配对及进程内 claim。broker Filled 不入账，费用完整的 ExecutionFill 才累计经济数量。CANCEL_PENDING 的部分成交保留撤单意图，取消后迟到成交经严格身份校验。真实 transport 始终锁闭；历史行情、backtest 与 trading.Fill 不变。

English: Implemented broker/ibkr mapping, separate identities, submit/cancel boundaries, raw callback normalization, error translation, execution/commission pairing and process-lifetime claims. Broker Filled is not booked; only fee-complete ExecutionFill records accumulate economics. Partial fills retain pending cancellation, and late cancelled fills require strict identity. Real order transport is always locked; historical data, backtest and trading.Fill are unchanged.

中文：默认 fixture 拦截真实网络和 IBKR 订单入口；内存 claim 不提供 crash durability。专用只读 smoke 需要 opt-in，未在线执行。关键 API、安全原因及本阶段文档提供双语说明。详细边界见 [IBKR execution](ibkr_execution.md)。

English: Default fixtures block real network and IBKR order entrypoints; memory claims provide no crash durability. The dedicated read-only smoke requires opt-in and has not run online. Critical APIs, safety rationale and Phase 3H documents are bilingual. See [IBKR execution](ibkr_execution.md).

## Phase 3I / Persistent Execution and Recovery

中文：在 `feature/phase-3i-paper-runner-recovery-foundation` 实现，尚未提交。新增 `infrastructure` 的 SQLite repository/claim、固定类型 JSON codec；`execution` 的纯恢复分类和快照核对；`broker/ibkr/recovery` 的身份与原始回调持久化；`application` 的薄 runner。订单版本、成交身份同事务保存；组合从已记账 Fill 重建，未记账成交可显式补记一次。故障测试覆盖 claim 前/后、transport 后、ack 后、execution/accounting 缺口、回调配对、事务回滚和并发 claim。

English: Implemented on `feature/phase-3i-paper-runner-recovery-foundation`, uncommitted. Adds SQLite repositories/claims and a fixed-type JSON codec in `infrastructure`, pure recovery classification and snapshot assessment in `execution`, durable identities/raw callbacks in `broker/ibkr/recovery`, and a thin `application` runner. Order versions and fill identities commit together. Portfolios rebuild from accounted fills; pending fills can be explicitly accounted once. Failure tests cover pre/post-claim, post-transport, post-ack, execution/accounting gaps, callback pairing, transaction rollback and concurrent claims.

中文：仅与已接受 Fill 精确关联的佣金等待可定向解除并保留审计；其他未决证据不因普通 ack、成交或重启清除；没有人工清除 API。旧会话 callback 恢复只是证据恢复，不恢复连接或新 session 的发送权限。详见 [execution recovery](execution_recovery.md)。

English: Only commission waits correlated with accepted fills are resolved, retaining audit records. True UNKNOWN, connection loss and other uncertainty remain latched across acknowledgements, fills and restarts; no manual-clear API is provided. Old-session callback recovery restores evidence only, not connections or dispatch authority in a new session. See [execution recovery](execution_recovery.md).

## 下一步 / Next

1. 人工审查 Phase 3I implementation、故障测试和事务边界；尚未 commit/push/merge。
2. 后续独立设计未决证据处置、审批 workflow、在线只读核对、完整 planning/reconciliation 与监控；真实 transport 保持锁闭。
3. Options、增量更新、分钟线时区和 corporate actions 继续作为独立能力设计。

1. Review Phase 3I implementation, failure tests and transaction boundaries; no commit/push/merge has been performed.
2. Separately design unresolved-evidence resolution, approval workflows, online read-only verification, full planning/reconciliation and monitoring; keep real transport locked.
3. Keep options, incremental updates, intraday timezone semantics, and corporate actions as separate capabilities.

当前安全限制保持不变：broker 只允许只读市场数据访问；broker-neutral 模拟订单不会提交到 IBKR，不包含自动执行。

The safety boundary is unchanged: broker access remains read-only; broker-neutral simulated orders are never submitted to IBKR and no automated execution is included.
