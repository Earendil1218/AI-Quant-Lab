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
