# 技术决策记录

本文件记录会长期影响项目架构、安全或维护方式的重要决定。普通代码修改、文件创建、Bug 修复和 Git 提交不在此记录。

历史决策原则上只追加、不覆盖。如果未来改变决定，应新增一条决策，说明替代了哪项旧决定及改变原因。早期决策只有月份记录时保留原日期精度，不补造具体日期。

每项新决策使用以下结构：

```text
日期
Decision
Context
Reason
Alternatives
Impact
```

## 2026-08：选择 Python 3.11

### Decision

选择 Python 3.11 作为项目的主要开发环境。

### Context

项目需要兼容 IBKR Python 生态和常用量化分析库。早期使用 Python 3.14 时遇到 `ib_insync` 兼容问题。

### Reason

- `ib_insync` 在 Python 3.11 环境中已经验证可用
- 金融量化生态支持成熟
- 当前阶段稳定性和可学习性优先于使用最新解释器版本

### Alternatives

- 继续使用 Python 3.14 并自行处理兼容问题
- 使用其他较旧或较新的 Python 版本
- 使用 Anaconda 管理环境

### Impact

- 项目主要虚拟环境采用 Python 3.11
- 新依赖应先检查 Python 3.11 兼容性
- 未来升级 Python 时需要单独验证 IBKR 连接和测试套件

## 2026-08：研究阶段统一使用 TWS API 只读连接

### Decision

在研究与数据获取阶段，TWS API 连接统一使用 `readonly=True`，并连接 IBKR Paper Trading。

### Context

当前项目只需要读取历史市场数据，不需要由代码管理订单。研究脚本与交易能力混合会增加误操作风险。

### Reason

- 防止研究代码意外提交订单
- 使当前权限与实际数据需求一致
- 将订单能力推迟到具备独立风控、审计和审批机制的阶段

### Alternatives

- 使用非只读 Paper Trading 连接
- 直接连接真实账户
- 在同一模块中同时实现数据与订单功能

### Impact

- 当前连接模块默认只读
- 当前代码只允许数据访问，不实现订单提交、修改或撤销
- Paper Trading 自动执行和 Live Trading 必须作为未来独立阶段重新设计并审批

## 2026-08-14：采用模块化职责边界

### Decision

将配置、IBKR 连接、市场数据访问和应用流程编排拆分为独立模块。

### Context

早期代码以连接和历史数据测试脚本为主，配置、外部 API 调用、数据转换和输出流程混在一起，不利于测试和后续扩展。

### Reason

- 单一职责使代码更容易理解和维护
- 外部连接与数据转换可以分别验证
- 主程序只负责编排，避免重复底层细节
- 为未来的数据存储、研究和回测提供稳定接口

### Alternatives

- 继续维护单文件脚本
- 立即引入完整应用框架或复杂依赖注入体系

### Impact

- `config` 管理运行参数
- `broker.connection` 管理 IBKR 连接
- `broker.market_data` 管理股票历史数据访问和转换
- `main.py` 只负责编排与测试结果输出
- 后续模块应遵守相同的职责边界，除非新增决策明确调整

## 2026-08-14：broker 与数据持久化分离

### Decision

broker 层只负责外部券商连接和数据访问，不负责 CSV、Parquet、数据库或其他持久化操作。

### Context

历史数据获取和本地保存具有不同的变化原因。将两者混在同一个函数中会使测试、复用和未来更换存储方案变得困难。

### Reason

- 保持数据来源与存储方式解耦
- 允许同一 DataFrame 被不同研究或存储流程复用
- 便于分别测试 IBKR 请求和文件读写

### Alternatives

- 在历史数据请求函数中直接保存文件
- 让主程序长期承担全部存储细节
- 当前阶段直接引入数据库和 ORM

### Impact

- `fetch_stock_history` 只返回 DataFrame
- Phase 2 将独立设计简单的数据存储与更新层
- 未来更换文件格式或数据库时，不应要求修改 broker 请求逻辑

## 2026-08-14：按当前需求保持最小依赖和简单实现

### Decision

项目按阶段只引入当前能力直接需要的依赖和抽象；第一阶段不引入数据库、ORM、复杂 logging、自定义异常体系、Docker 或交易框架。

### Context

项目处于学习和基础建设阶段。过早引入基础设施会增加认知负担，并掩盖数据链路和模块职责本身的问题。

### Reason

- 降低学习和维护成本
- 让每个新增组件都有明确需求支撑
- 优先建立可工作的最小闭环和基础测试

### Alternatives

- 预先搭建完整生产级平台
- 使用数据库、容器和框架一次性覆盖未来需求

### Impact

- `requirements.txt` 当前只记录直接运行依赖
- 新依赖和高级抽象需要结合具体阶段重新评估
- “暂不引入”不是永久禁止；需求成熟时应通过新决策说明选择

## 2026-08-14：订单与 Live Trading 必须获得明确人工审批

### Decision

任何新增订单提交、修改、撤销、自动化 Paper Trading 或 Live Trading 能力，都必须先进行专项设计和安全审查，并获得用户明确批准。

### Context

数据研究权限不能自然延伸为交易权限。即使使用模拟账户，订单逻辑也会引入状态同步、重复提交、风控和故障恢复等新风险。

### Reason

- 防止研究任务被误解为交易授权
- 确保执行能力具备风险检查、审计和停止机制
- 将真实资金风险与普通开发任务严格隔离

### Alternatives

- 将 Paper Trading 视为默认可执行环境
- 在现有 broker 模块中顺便增加订单方法
- 从模拟交易直接扩展到真实交易

### Impact

- 当前代码不得包含订单能力
- 每个交易阶段需要独立计划、确认、实施和验证
- 路线图中出现 Live Trading 只代表长期研究方向，不构成执行授权

## 2026-08-15：Phase 2 原始市场数据采用 CSV

### Decision

Phase 2 使用 CSV 作为原始历史市场数据的首版本地存储格式，并采用 `SYMBOL_INTERVAL.csv` 命名规则。

### Context

项目需要将 IBKR 返回的 DataFrame 保存到本地并可靠地重新加载，从而避免每次研究都重新请求 TWS。当前阶段重点是学习和验证数据链路，而不是建设生产级数据平台。

### Reason

- CSV 结构直观，便于人工打开和检查
- pandas 原生支持读写，不需要新增存储引擎
- 适合当前单标的、日线、小规模数据
- 有利于先验证文件命名、目录边界、日期恢复和数据质量流程

### Alternatives

- Parquet：类型和空间效率更好，但当前规模尚不需要额外格式依赖和复杂度
- SQLite、DuckDB 或 PostgreSQL：适合更复杂查询或更大规模数据，但超出 Phase 2 范围
- 每次研究重新请求 IBKR：实现简单，但依赖 TWS 在线状态且产生重复请求

### Impact

- 原始行情保存在 `data/raw/`，当前日线文件示例为 `NVDA_1d.csv`
- 真实行情文件由 `.gitignore` 排除，不进入 Git
- broker 仍只返回 DataFrame，不负责持久化
- storage 模块负责 CSV 命名、保存和读取
- CSV 是当前阶段选择，不永久排除未来使用 Parquet 或数据库；需求改变时应新增决策记录

## 2026-08-17：Phase 3 建立确定性的 processed market data 边界

### Decision

新增独立 `data.processing` 模块，将原始行情标准化为固定的 `date, open, high, low, close, volume` schema，并将结果保存到 `data/processed/`。重复时间戳默认报错，不自动删除。

Add an independent `data.processing` module that normalizes raw history into the fixed `date, open, high, low, close, volume` schema and persists it under `data/processed/`. Duplicate timestamps raise an error and are not removed automatically.

### Context

Phase 2 已能获取、验证和保存 IBKR 原始 CSV，但研究层仍会接触数据源特有字段、类型和索引。Phase 3 需要建立稳定且不依赖 broker 细节的数据输入边界。

Phase 2 could fetch, validate, and persist raw IBKR CSV data, but research code would still be exposed to source-specific fields, dtypes, and indexes. Phase 3 requires a stable input boundary independent of broker details.

### Reason

- validation、processing 和 storage 具有不同的变化原因，应保持独立。
- 稳定 schema 可以供未来 research、indicators、strategy 和 backtest 复用。
- 无来源优先级时自动保留 first 或 last 可能掩盖行情冲突。
- 纯 DataFrame processing 易于离线测试且无需新增依赖。

- Validation, processing, and storage change for different reasons and remain separate.
- A stable schema can support future research, indicators, strategy, and backtesting modules.
- Keeping the first or last duplicate without source priority could conceal a market-data conflict.
- Pure DataFrame processing is deterministic, offline-testable, and requires no new dependency.

### Alternatives

- 在 validation 中直接修改和清洗数据。
- 在 storage load/save 时隐式标准化数据。
- 自动 `drop_duplicates(keep="first")` 或 `keep="last"`。
- 立即引入 schema framework、pipeline class 或数据库。

### Impact

- `process_market_data` 不原地修改输入，并输出固定列顺序、类型、时间顺序和 index。
- raw 数据保留数据源形态，processed 数据成为后续研究层的标准输入。
- 分钟线时区、多数据源 reconciliation、增量更新和 corporate actions 出现真实需求后，需要重新评估当前设计。

- `process_market_data` does not mutate its input and returns stable column order, dtypes, chronological order, and index.
- Raw data preserves the source representation; processed data becomes the standard research-layer input.
- Intraday timezone handling, multi-source reconciliation, incremental updates, and corporate actions will require reassessment when those needs become real.

## 2026-08-19：Research 与 Data 正式分层

### Decision

新增独立 `research` package。`data` 层继续定义市场数据应具有的结构，`research` 层只定义从标准数据计算什么；研究函数不连接 broker、不读取固定路径，也不负责持久化。

Add an independent `research` package. The `data` layer continues to define what market data should look like, while `research` defines only what is calculated from normalized data. Research functions do not connect to brokers, load fixed paths, or persist results.

### Context

Phase 3A 已建立稳定 processed OHLCV contract。收益率和统计属于派生研究指标；将其写入 processing 会混合数据标准化与金融计算，并让未来 indicator、strategy 和 backtest 难以复用清晰边界。

Phase 3A established a stable processed OHLCV contract. Returns and statistics are derived research metrics. Placing them in processing would mix normalization with financial calculation and weaken reuse by future indicators, strategies, and backtests.

### Reason

- processing 与 research 有不同的变化原因。
- 纯 DataFrame/Series API 可确定性离线测试。
- 研究结果可以被 notebook、strategy、backtest、portfolio 和 risk 层复用。
- 当前需求不需要 research engine、pipeline framework 或数据访问抽象。

- Processing and research change for different reasons.
- Pure DataFrame/Series APIs are deterministic and offline-testable.
- Research results can be reused by notebooks, strategy, backtest, portfolio, and risk layers.
- The current scope does not require a research engine, pipeline framework, or data-access abstraction.

### Alternatives

- 将收益计算加入 `data.processing`。
- 让 research API 自行读取 processed CSV。
- 提前建立通用 research pipeline 或 class hierarchy。

### Impact

- `research.returns` 提供 simple、log 和 cumulative return。
- `research.statistics` 提供 typed summary 和显式 annualization 假设。
- 当前 close 未确认经过 corporate-action adjustment，因此输出定义为 price return，而不是 total shareholder return。
- performance metrics、策略和回测继续保留在后续独立层。

## 2026-08-22：日期化研究采用精确交集与统一共同样本

### Decision

日线 Research API 使用无时区、唯一且升序的 `DatetimeIndex`。多资产与 benchmark 比较采用真实收益日期的精确交集，不 forward-fill、不 backward-fill，也不把缺失收益视为零。相关矩阵中的所有资产统一使用同一个共同日期样本，不使用 pairwise available observations。

Daily research APIs use a timezone-naive, unique, ascending `DatetimeIndex`. Multi-asset and benchmark comparisons use the exact intersection of observed return dates without forward filling, backward filling, or treating missing returns as zero. Every entry in a correlation matrix uses one shared common-date sample rather than pairwise available observations.

### Context

Phase 3C 引入 benchmark、active return、tracking error 和多资产 correlation。若不同资产使用不同观察日期或通过填充制造收益，比较结果将不再具有统一的样本含义。

Phase 3C introduces benchmarks, active returns, tracking error, and multi-asset correlation. Comparisons lose a consistent sample interpretation if assets use different observation dates or if returns are manufactured by filling gaps.

### Reason

- 缺失收益不等于零收益。
- active return 必须对应同一日期的资产和 benchmark 收益。
- correlation matrix 使用统一样本后，各 pair 的结果更可比较。
- timezone-naive 日线契约与当前 processed data 一致；分钟线、多市场和交易所 calendar 需要未来独立设计。

- A missing return is not a zero return.
- Active returns require asset and benchmark observations from the same date.
- A shared correlation sample makes results across pairs more comparable.
- The timezone-naive daily contract matches current processed data; intraday, multi-market, and exchange-calendar semantics require a separate future design.

### Alternatives

- 对缺失日期 forward-fill、backward-fill 或补零。
- 允许 pandas 在未经统一对齐的 Series 上隐式比较。
- correlation 对每个资产 pair 使用不同的可用日期。
- 在尚未支持分钟线前引入通用时区和 calendar framework。

### Impact

- leading NaN 只表示第一日没有 previous price，对齐前移除；内部或末尾 NaN 明确拒绝。
- benchmark 累计曲线从同一共同起点开始。
- Research 继续只处理内存 DataFrame/Series，不连接 broker 或执行文件 I/O。
- Phase 3C 后暂停无边界增加研究指标；Signal/Strategy 与 Options 两条后续方向需重新评审。

- A leading NaN only marks the absence of a previous price on the first date and is removed before alignment; internal or trailing NaN is rejected.
- Benchmark cumulative curves start from the same common observation.
- Research continues to operate only on in-memory DataFrames/Series without broker access or file I/O.
- After Phase 3C, unbounded metric expansion pauses; Signal/Strategy and Options remain alternative directions for the next review.

## 2026-08-29：Signal、Strategy Intent 与 Execution 分层

### Decision

Trailing indicators 保留在 `research`；signal generation、Strategy abstraction 和 target-position intent 位于独立 `strategies` package。Signal 描述市场状态，Strategy 将状态转换为目标敞口。Strategy 不生成订单，也不访问 broker、账户、现金或实际持仓。

Trailing indicators remain in `research`; signal generation, the Strategy abstraction, and target-position intent live in the independent `strategies` package. A signal describes market state, while a Strategy maps that state to desired exposure. Strategies do not create orders or access brokers, accounts, cash, or actual positions.

### Context

Phase 3D 需要建立未来 Backtest Engine 可稳定消费的边界，同时避免研究规则与执行状态耦合。当前 reference strategy 只需要单资产 long/flat 表达，不需要订单模型或通用事件系统。

### Reason

- `research` 回答指标是多少，signal 回答发生了什么，Strategy 回答期望持有什么。
- date-indexed target position 可被未来 backtest 直接消费，而不暴露策略内部规则。
- `SignalState` Enum 与 `Strategy` abstraction 固定公共语义；DataFrame 保持批量研究接口简单。
- 冻结的策略参数保证配置稳定，纯内存计算保证确定性和可测试性。

### Warm-up and look-ahead policy

- Moving average 使用 trailing complete windows（`min_periods=window`）。
- slow window 完成前 signal 为 `unavailable`，target position 为 `NaN`；未知状态不自动视为 flat、long 或 short。
- 不 backward-fill。每个日期的结果只使用该日期及此前观察；修改或追加未来数据不得改变历史结果。

### Impact

- 公共 intent contract 为无时区、唯一、升序日期索引上的 `signal_type`、`signal_state` 与 float64 `target_position`；当前值为 `1.0` long、`0.0` flat、`NaN` unavailable。
- MA crossover 仅用于验证架构，不声明投资有效性。
- Backtest、portfolio/risk 与 execution 负责未来的成交时点、仓位约束、现金、费用、滑点和订单；这些不属于 Strategy。
- 当前不引入 event bus、async、数据库、message queue 或 broker integration。

## 2026-08-29：Target Exposure、Sizing 与 Quantity 分层

### Decision

Phase 3D `target_position` 在 trading-domain boundary 中解释为 standardized target exposure：`1.0` 是 desired long state，`0.0` 是 desired flat state。它不代表 shares、NAV percentage、notional allocation 或固定金额。独立 `SizingPolicy` 将 `TargetExposureIntent` 转换为 `TargetQuantity`；Phase 3E 只实现确定性的 `FixedQuantitySizing`。

### Reason

- Strategy 决定期望状态，sizing 决定规模，portfolio reconciliation 决定交易差额。
- 股票、期权及未来 risk-based sizing 可以共享 Strategy contract。
- fixed quantity 是当前实现范围，不是长期 architecture limitation。

### Impact

- Portfolio planning 不硬编码 long quantity。
- warm-up intent 不进入 quantity reconciliation，也不创建订单。
- 当前只接受 `0.0`、`1.0` 或 unavailable；NAV/notional/volatility/option sizing 延后。

## 2026-08-29：Order 与 Fill 分离，Fill 驱动 Portfolio Accounting

### Decision

`OrderRequest` 是 broker-neutral 执行请求，不改变 portfolio。只有已完成的 `Fill` 可以改变 cash 和 position quantity。Phase 3E 不加入 average cost，因为当前 mark-to-market 和 equity contract 不需要它，且 commission/cost-basis semantics 尚未进入需求。

### Reason

- 创建订单不等于成交。
- simulated execution 和未来 broker adapter 可以产生同一种 Fill record。
- 避免未定义的 partial reduction、full close 和 commission cost-basis behavior。

### Impact

- precise accounting 使用 Decimal；research、strategy 和 OHLCV DataFrame 保持 float64。
- `BacktestResult` 保存 Decimal domain records，并提供 float64 pandas equity-curve view。
- PlanningDecision（是否需要订单）与 ExecutionRejectionReason（为何不能成交）使用不同语义层。

## 2026-08-29：Daily Backtest 使用 T Close Decision 与 T+1 Open Execution

### Decision

Phase 3E daily lifecycle 固定为：OPEN 执行前一 close 的 pending order；CLOSE mark-to-market、创建 end-of-day snapshot、观察完整 bar、生成下一 intent 与 pending order。T close signal 禁止在同一 T close 成交。

### Reason

- 日线数据无法证明在完整 T close 已知后仍可按该 close 成交。
- next-open rule 对 signal、order 和 fill 时间提供明确可测试的因果边界。
- Engine 每日只向 Strategy 提供截至当日的 history prefix，从编排层阻断 future data。

### Impact

- 最后一个 bar 产生的订单记录 `NO_NEXT_BAR` rejection。
- insufficient cash 是 execution feasibility rejection，不与 target planning decision 混合。
- 第一版仅支持 single equity、daily bars、long/flat、no leverage/no short，以及 fixed commission 和 basis-point slippage。
- 所有 order/fill 都是离线模拟；broker 继续保持 IBKR read-only market-data boundary。

## 2026-09-01：Pre-Trade Risk 与 Execution Handoff 分层

### Decision

Phase 3F 在 broker-neutral `OrderRequest` 与 execution 之间建立独立、确定性的 pre-trade risk boundary。`RiskConfiguration` 只启用显式配置的规则；`BacktestEngine.risk_configuration=None` 明确表示 risk layer disabled。一旦调用 `evaluate_order_risk`，evaluation 即严格 fail closed。

Phase 3F establishes an independent, deterministic pre-trade risk boundary between a broker-neutral `OrderRequest` and execution. `RiskConfiguration` enables only explicitly configured rules; `BacktestEngine.risk_configuration=None` explicitly means that the risk layer is disabled. Once `evaluate_order_risk` is called, evaluation is strictly fail-closed.

### Context

Phase 3E 已能从 strategy intent 生成 order 并在 next OPEN 模拟成交，但没有策略无关的 risk decision。直接建立 broker lifecycle 会使 risk approval、submission authority、broker rejection 和 fill 混合。

### Reason

- Risk 消费 `OrderRequest`、`PortfolioState`、`ValuationContext` 和 `RiskConfiguration`，不访问 Strategy 或 IBKR。
- `RiskDecision.evaluated_at` 使用 `ValuationContext.observed_at`，不读取 wall clock，保证相同输入产生相同结果。
- BUY resulting quantity 定义为 current + order，SELL 定义为 current - order；负结果以 `SHORT_POSITION_NOT_ALLOWED` 拒绝。
- `allowed_instruments=None` 表示规则未启用；empty `frozenset` 表示不允许任何 instrument；配置只接受 `InstrumentId`。
- 第一版按固定顺序返回 first rejection，保持小 API 和确定性。
- Risk approval 只表示通过风险检查，不表示 human approval、submission authorization、broker acknowledgement 或 Fill。

### Backtest timing

Phase 3F 的 daily backtest 在真正到达 T+1 OPEN 时统一执行 risk evaluation，并使用该 OPEN 估值检查 equity order notional。这是当前 application timing，不是所有 risk rules 的领域必然要求；allowed-instrument 和 quantity rules 本身不依赖价格。未来真实 execution 可以拆分 static 与 valuation-dependent checks，但本阶段不建立第二套 pipeline。

最后一根 bar 在 close 生成的 pending order 没有 T+1 OPEN，也就没有 risk evaluation horizon。它继续直接产生 `ExecutionRejection(NO_NEXT_BAR)`，不使用 last close 代替 OPEN，也不产生 `RiskDecision`。因此 `orders` 数量不一定等于 `risk_decisions` 数量。

### Alternatives

- 未配置 risk 时隐式创建 permissive configuration。
- 在 T close 使用 close price 风控所有 pending orders。
- 将 risk、broker 和 simulation failures 放入同一个 rejection enum。
- 现在引入完整 execution package、ClientOrderId 或 `ApprovedOrder` wrapper。

### Impact

- Risk evaluation 不修改 `PortfolioState`，不创建 Fill。
- `INSUFFICIENT_CASH` 继续属于 execution/accounting feasibility；`NO_NEXT_BAR` 继续属于 backtest execution rejection。
- Equity notional 明确为 price × quantity，且只支持 `AssetClass.EQUITY`；需要估值规则时，未知 asset class fail closed。
- Phase 3F 只定义 execution handoff。ClientOrderId、idempotency、submission、broker lifecycle 和 reconciliation 延后到 Phase 3G。
- Broker 继续只允许 IBKR readonly market-data access；本决定不授权任何订单 API。

## 2026-09-03：Broker-Neutral Execution Lifecycle 独立分层

### Decision

新增独立 `execution` package，管理本系统生成的 `ClientOrderId`、显式 `SubmissionAuthorization`、immutable `ExecutionOrder`、broker identity、partial-fill provenance、optimistic repository contract 和 reconciliation-friendly observations。`OrderRequest` 继续只表达交易经济意图，`trading.Fill` 继续只表达经济成交；两者均不承载 stateful execution identity。

### Reason

- Risk approval 只证明 financial/pre-trade checks passed，不是 human approval 或 submission permission；submission 必须绑定单独的成功型 authorization capability。
- `ClientOrderId` 在 execution lifecycle 创建时由系统生成并保持稳定；`BrokerOrderId` 和 `BrokerExecutionId` 是可选外部身份，不能替代本地 identity。
- 外部 submission 具有无法原子提交本地状态和 broker side effect 的 dual-write 风险，因此必须先保存 `AUTHORIZED → SUBMISSION_PENDING`，未来 adapter 才能发送请求。
- timeout/disconnect 后的 `UNKNOWN` 不是失败；它表示 broker 是否收到请求不可确定，禁止自动重提并只能经 reconciliation 或 operator resolution 收敛。
- `ExecutionFill` 为现有 economic `Fill` 增加 client/fill/broker execution provenance，使 multiple fills 和 duplicate delivery 可在 portfolio accounting 之前处理，而不破坏已有 Fill contract。

### Repository and idempotency

`ExecutionOrderRepository` 提供 `add/get/save(expected_version)` contract。`InMemoryExecutionOrderRepository` 仅用于 Phase 3G、unit tests 和 offline development，不提供 process crash、restart 或 durable persistence guarantee。相同 `ClientOrderId` 只能从 `AUTHORIZED` 一次进入 `SUBMISSION_PENDING`；optimistic version 防止 stale overwrite；相同 fill identity replay 不重复增加 cumulative quantity，并通过 acceptance flag 阻止重复 portfolio application。

### Boundaries and impact

- Phase 3G 不修改 `BacktestEngine`：deterministic historical simulation 没有 network timeout、broker acknowledgement 或 restart reconciliation，不应被强制包装成 broker workflow simulator。
- `risk` 不依赖 `execution`；execution 可以消费现有 `RiskDecision` contract 来验证 authorization binding。
- `broker/` 保持 read-only market-data boundary，不增加 `placeOrder`、`cancelOrder`、order callbacks 或 query APIs。
- IBKR adapter 和 identity mapping 延后到 Phase 3H；persistent repository、human approval workflow、Paper runner、automatic recovery、outstanding-order-aware planning、broker/local portfolio reconciliation、monitoring 和 alerts 延后到 Phase 3I。
- 本决定不提供 Paper 或 Live Trading 授权，也不建立完整 OMS。

## 2026-09-07：Phase 3H IBKR execution boundary / 执行边界

### 决定 / Decision

中文：采用 broker/ibkr 子包，将 ib-insync 0.9.86 原始 callback、合约和身份限制在 adapter 内。execution 增加中立 dispatch/result、一次性 claim 和显式观察规则。真实 transport 始终锁闭；专用 session 只支持显式只读 smoke。保留历史 connection/main.py 的行为。

English: Use broker/ibkr to contain ib-insync 0.9.86 raw callbacks, contracts and identities. Add neutral dispatch/results, one-shot claims and explicit observation rules to execution. Real order transport remains locked; the dedicated session supports explicit read-only smoke only. Preserve historical connection/main.py behavior.

### 原因与取舍 / Rationale and tradeoffs

- 中文：仅检查 SUBMISSION_PENDING 不阻止两个调用者同时发送。共享内存 claim 按 ClientOrderId/operation 原子消费，绑定保存版本与请求；不提供 crash durability、数据库、lease 或 retry。
- English: Checking SUBMISSION_PENDING alone does not stop concurrent senders. Shared memory claims atomically consume ClientOrderId/operation, binding the saved version/request, without crash durability, databases, leases or retries.
- 中文：permId=0 保持未知；正 permId 才生成账户命名空间的 BrokerOrderId。完整 execId 派生稳定 ExecutionFillId，冲突不可覆盖。
- English: permId=0 remains unknown; positive permId produces account-namespaced BrokerOrderId. Complete execId derives stable ExecutionFillId; conflicts cannot overwrite bindings.
- 中文：ib_insync 高层状态可能本地合成，因此捕获原始 wrapper callback。broker Filled 不增加经济 quantity。等待真实佣金配对再生成 Fill，保留 trading.Fill 和回测不变。
- English: ib_insync can synthesize high-level states, so capture raw wrapper callbacks. Broker Filled does not increase economic quantity. Wait for actual commission pairing before constructing Fill, preserving trading.Fill and backtest.
- 中文：applied_at 与 execution_time 分离；撤单期间部分成交保持 CANCEL_PENDING；取消后迟到成交走专用 observation 校验，不开放任意 transition。
- English: Separate applied_at from execution_time. Partial fills preserve CANCEL_PENDING; late cancelled executions use explicit observation validation, not arbitrary transitions.
- 中文：旧 reconciliation API 保持签名和返回类型，取消直接写入累计数量的行为；broker quantity 仅为比较证据，ExecutionFill 是经济事实来源。UNKNOWN 的成交状态只有在已有匹配成交明细时才能确认，否则保持 UNKNOWN 并通过 reconcile_order 报告差异。
- English: Keep the legacy reconciliation signature and return type while removing quantity writes. Broker quantities are comparison evidence; ExecutionFill is the economic source of truth. Fill-state observations resolve UNKNOWN only with matching accepted execution details; otherwise UNKNOWN remains and reconcile_order reports mismatches.
- 中文：采用 prepare → revalidate → claim → side effect。准备失败或快照过期不消费 claim，也不分配 broker identity；claim 锁内重验完整保存快照，仍保证并发至多一次。消费后不 release、不 retry。
- English: Use prepare → revalidate → claim → side effect. Failed/stale preparation consumes neither claim nor broker identity. Full saved-snapshot revalidation under the claim lock preserves concurrent at-most-once entry. Consumed claims have no release or retry.
- 中文：UNKNOWN 保留所有已知成交与身份事实。CANCELLED 表示剩余未成交部分取消；迟到部分成交保持 CANCELLED，累计满额进入 FILLED，重复佣金不重复接受经济成交。
- English: UNKNOWN preserves known execution and identity facts. CANCELLED cancels the unfilled remainder; late partial fills retain CANCELLED and complete fills become FILLED. Repeated commissions never cause duplicate economic acceptance.
- 中文：端口、readonly 与账户前缀不能证明 Paper。真实发送没有可验证持久化/恢复基础，所以即使 opt-in 也保持锁闭；不以一次 Paper 下单证明工程正确性。
- English: Port, readonly and account prefixes cannot prove Paper safety. Real dispatch lacks verified durability/recovery, so remains locked even with opt-in; one successful Paper order would not establish engineering correctness.

### 后续 / Deferred

中文：持久化、恢复、approval workflow、runner、未完成订单 planning、周期/组合 reconciliation、audit/monitoring 留给 Phase 3I。新版 CommissionAndFeesReport 仅是未来迁移事项，不修改本版经济模型。关键 API、安全 WHY 注释及 Phase 3H 文档必须双语可读。

English: Persistence, recovery, approval workflow, a runner, outstanding-order planning, periodic/portfolio reconciliation and audit/monitoring remain Phase 3I. New CommissionAndFeesReport APIs are a future migration topic, not a change to current economics. Critical APIs, safety WHY comments and Phase 3H documents must remain bilingual.

详细设计与依据 / Detailed design and sources: [IBKR execution foundation](ibkr_execution.md).

## 2026-10-06：Phase 3I SQLite persistence / 持久化与恢复

中文：选用标准库 SQLite，避免 ORM 与外部服务；domain model 与 repository protocol 保持稳定，SQLite 位于 `infrastructure`，薄 runner 位于 `application`。一个数据库对应一个执行/组合作用域，调用方串行化 planning/dispatch/state writes。金额用 Decimal 字符串，时间保留原语义，固定类型 JSON 不使用 pickle。

English: Choose standard-library SQLite without an ORM or external service. Keep domain models/repository protocols stable; place SQLite in `infrastructure` and the thin runner in `application`. One database represents one execution/portfolio scope with serialized planning/dispatch/state writes. Decimal uses strings; timestamps retain their semantics; allowlisted JSON replaces pickle.

中文：aggregate version、接受的 Fill 和去重身份同事务保存；`UPDATE ... WHERE version=?` 拒绝 stale writer。claim 原子绑定已保存 pending 快照，在 transport 前提交，不提供释放接口。claim 后崩溃保留原生命周期并分类为 RECONCILIATION_REQUIRED；UNKNOWN 不是 FAILED，不允许自动 resubmit。

English: Aggregate version, accepted fills and dedup identities commit together; version-qualified UPDATE rejects stale writers. A claim atomically binds the saved pending snapshot and commits before transport with no release API. Post-claim crashes preserve lifecycle and classify as RECONCILIATION_REQUIRED. UNKNOWN is not FAILED and never permits automatic resubmit.

中文：Fill ledger 与唯一 accounting marker 解决成交/记账缺口。组合由初始现金和已记账 Fill 重建；补记在单独事务中验证全部经济变动并保存标记，不在提交前修改外部组合。原始 callback 先持久化，再重建既有 normalizer；固定批次观察提交后才标记 inbox 已处理。无论 inbox marker 前后崩溃，经济去重保持有效。

English: A fill ledger and unique accounting markers close the execution/accounting gap. Portfolios rebuild from initial cash and accounted fills. A separate accounting transaction validates economics and saves markers without mutating external portfolios before commit. Raw callbacks persist before reconstructing the existing normalizer; a fixed inbox batch is acknowledged only after neutral observations commit. Economic dedup survives crashes on either side of inbox acknowledgement.

中文：纯 reconciliation 复用 BrokerOrderObservation，不根据 quantity snapshot 记账，也不根据 missing 订单自动重发。较旧 ack 不清除新的 UNKNOWN；未决观察保守锁存，除下述精确匹配的佣金等待外无清除 API。真实 transport 仍锁闭，未实现网络 runner、审批 workflow、自动 retry、完整 reconciliation loop、多进程协调和 HA。SQLite 不与 broker 形成分布式事务。

English: Pure reconciliation reuses BrokerOrderObservation, never books quantity snapshots or resends missing orders. Old acknowledgement replay cannot clear newer UNKNOWN; unresolved observations remain latched except for the correlated commission waits described below. Real transport stays locked. Network runners, approval workflows, automatic retry, full reconciliation loops, multi-process coordination and HA remain excluded. SQLite does not create a distributed transaction with the broker.

设计、故障窗口与测试依据 / Design, crash windows and test evidence: [execution recovery](execution_recovery.md).

## 2026-10-06: Phase 3I pre-commit safety fixes / 提交前安全修复

中文：一次性规划票据绑定完整计划、风险决策及组合 revision；schema v2 强制 broker 身份归属、跨会话修正族与定向佣金等待解除。整股 float 仅在 broker 数量边界转整数；固定 Decimal context 拒绝精度损失。无旧 schema 自动迁移，真实 transport 保持锁闭。

English: Persist one-use PlanningTickets binding portfolio revision, complete plan and risk decision; validate freshness during preparation, dispatch and claim. SQLite schema v2 adds bidirectional broker ownership, cross-generation account/execution families and correlated observation resolution; v1 has no automatic migration. Canonicalize integral floats only at broker callback quantity boundaries. Resolve only commission waits matching accepted fills, retaining other UNKNOWN evidence. Rebuild portfolios under an explicit precision-50, ROUND_HALF_EVEN Decimal context; fail on precision loss without cent quantization. No correction accounting, automatic retry or transport unlocking is added.

## Phase 3K — Controlled Paper boundary decisions

- 保留 ReadOnlyIBKRTransport 的真实 submit/cancel/ID 锁；新增独立 PaperExecutionTransport，复用 owned IB、raw wrapper 与 session/query seams。
- 默认关闭，必须同时具有 config PAPER/side-effect intent、双重调用方显式 opt-in、当前 generation/exact account 的独立人工 Paper 确认，以及 durable planning/risk/SubmissionAuthorization/claim/ownership。环境变量与 risk PASS 都不是人工授权。
- 固定构造时 config/generation 快照，发送前反复核验实际 session endpoint 与 managed accounts；disconnect 使旧实例失效，不重连、不重发。
- SQLite claim 在 qualification/order preparation/preflight 之后、分配 broker ID 之前永久提交；claim 后 NOT_SENT 也不释放，placeOrder 入口后的异常一律 UNKNOWN。
- 真实 SELL 延后：local long inventory 不能证明 broker long inventory，3K 不同步 positions，故无法保证 SELL 不开空。保留 broker-neutral SELL 映射；可信 broker inventory 交给 3L。
- 真实 cancellation 延后：保留已有离线 lifecycle/adapter API，真实入口锁闭，不牺牲 uncertain cancel 的状态正确性。
- 新增薄 runner startup/ingestion/fresh-query 编排和非 pytest 自动入口的有界人工验收函数；pytest 的真实订单禁用规则保持不变。
- 只允许 fee-complete full fills 定向审计解决确切身份匹配的历史 pending/held/completion hints。保留 raw observations；不清除 UNKNOWN、disconnect、quantity conflict 或其他未知证据。
- Paper 类型是独立人工部署确认的信任输入；Socket session endpoint/account evidence 不提供可靠 Paper/Live 类型证明，不宣称能识别虚假确认或任意重配 TWS。

English: Phase 3K is the first controlled Paper side-effect capability. Online Paper integration is opt-in only. It is not automated trading, strategy runtime, Live Trading, or account/portfolio synchronization. Phase 3J was merged in PR #11 (`bdf08e8`, feature `a74e0cd`); Phase 3K remains local and uncommitted pending review. No real online order acceptance was performed.

## Pre-commit safety audit / 提交前安全审查

发送 scope 已改为内部 `_dispatch_scope`，入口验证尚未消费的 durable claim，避免用已消费 claim 重入并绕过 adapter；公开 `place/next_order_id` 没有内部 scope 时仍拒绝。边界使用确切 OrderSide.BUY，并重新核对获授权 instrument 与 spec。连接期 disconnect、connectivity/recovery notice 或未知诊断永久退役该 generation，连接返回不得恢复权限。

未知 broker diagnostic 在 durable inbox replay 阶段保存 review-required blocker，所以即使在 raw commit 后、normalization 前崩溃，重启重放也不会因无订单关联而清除阻塞。信息类通知不会伪造未知状态。所有发送与重放仍是人工显式编排，没有 retry、SELL、cancel 或新功能。

Paper-only evidence remains operator-dependent; there is no cryptographically authoritative broker account type proof. Private IB objects/internal state are trusted application internals, not a security sandbox against arbitrary Python mutation. The library connection bootstrap may cache account/position responses in its own IB object; Phase 3K never consumes them as local cash/NAV/position truth or synchronizes them into local accounting.

Review evidence and verdict: [Phase 3K Pre-Commit Review Report](phase3k_precommit_review_report.md).
