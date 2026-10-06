# AI Quant Lab

## 项目简介 / Overview

### 中文

AI Quant Lab 是一个持续演进的量化研究项目，长期目标是建设具备真实工程质量的市场数据、研究、回测、期权、组合风险与执行平台。当前 Phase 3 已建立从 IBKR 原始历史行情到标准化 processed 数据、研究指标、信号、策略意图和确定性模拟成交的分层链路。

### English

AI Quant Lab is an evolving quantitative research project whose long-term goal is to become an engineering-focused platform for market data, research, backtesting, options, portfolio risk, and execution. Phase 3 now provides a layered deterministic path from raw IBKR history to processed data, research indicators, signals, strategy intent, and simulated fills.

## 项目起源 / Project Origin

### 中文

AI Quant Lab 是一个伴随学习过程逐步构建的个人量化研究项目。创建项目时，我并不是专业的 Python 开发者或量化开发者；Python 工程化、期权、Greeks、回测、Broker API 与量化系统架构等知识，都是从接近零基础开始学习。

因此，这个仓库不仅保存一个量化系统最终形成的代码，也记录它如何从基础阶段逐步成长为完整研究平台。项目采用持续迭代的方式推进：

**学习 → 设计 → 实现 → 测试 → 重构 → 再学习**

作者从零开始，但项目不会停留在初学者或教学演示水平。长期目标是建立一个开放、稳健并适合国际协作的量化研究平台，同时保留完整的成长轨迹。

### English

AI Quant Lab is a personal quantitative research project built progressively alongside my learning journey. When the project began, I was not an experienced Python or quantitative developer. I started learning Python engineering, options, Greeks, backtesting, broker APIs, and quantitative system architecture from almost zero.

The repository therefore records more than the final implementation of a quantitative system: it preserves how that system grows from its earliest foundations into a complete research platform. Development follows an iterative cycle:

**Learn → Design → Implement → Test → Refactor → Learn Again**

The author started from zero; the project does not have to remain at a beginner or tutorial level. Its long-term goal is an open, robust platform suitable for international collaboration while preserving the full development journey.

## 当前数据管道 / Current Data Pipeline

```text
IBKR TWS Paper Trading (readonly=True)
  → Fetch Historical Data
  → Validate Raw Data
  → data/raw/SYMBOL_INTERVAL.csv
  → Normalize Schema, Datetime, Dtypes, Order, and Index
  → Validate Processed Data
  → data/processed/SYMBOL_INTERVAL.csv
  → Reload and Validate
  → Output Summary
```

### 中文

Validation 判断数据是否有效；processing 决定数据如何标准化；storage 只负责路径和持久化。重复时间戳不会被静默删除，因为在没有可信来源优先级时，保留 first 或 last 都可能掩盖行情冲突。

当前标准 processed schema 为：

```text
date, open, high, low, close, volume
```

### English

Validation determines whether data is valid, processing defines how it is normalized, and storage owns only paths and persistence. Duplicate timestamps are never removed silently because keeping the first or last row without a trusted source priority could hide a market-data conflict.

The current processed schema is:

```text
date, open, high, low, close, volume
```

## 项目结构 / Project Architecture

```text
AI-Quant-Lab/
├── main.py              # End-to-end historical data pipeline
├── config/              # Environment and path configuration
├── broker/              # Read-only market data; ibkr/ execution adapter with locked transport
├── data/
│   ├── validation.py    # Data-quality rules
│   ├── processing.py    # Deterministic market-data normalization
│   ├── storage.py       # CSV paths, save, and load
│   ├── raw/             # Source-level historical CSV files
│   └── processed/       # Normalized research-ready CSV files
├── tests/               # Offline tests with no real TWS dependency
├── docs/                # Context, status, decisions, roadmap, and workflow
├── notebooks/           # Exploratory research
├── research/            # Pure returns, statistics, and indicators
├── pricing/             # Future options pricing and Greeks
├── strategies/          # Pure signals and target-position intent
├── trading/             # Broker-neutral instruments, intents, orders, and fills
├── portfolio/           # Sizing, target reconciliation, and fill accounting
├── backtest/            # Deterministic daily simulation and analytics view
├── risk/                # Broker-neutral deterministic pre-trade risk controls
├── execution/           # Broker-neutral identity, lifecycle, recovery and reconciliation
├── infrastructure/      # SQLite execution repository, durable claims and fill accounting
└── application/         # Explicit offline Paper runner orchestration
```

## 运行环境 / Requirements

- Python 3.11
- pandas
- ib-insync
- IBKR TWS Paper Trading，仅在线获取数据时需要 / required only for online data acquisition

```powershell
python -m pip install -r requirements.txt
```

## 配置 / Configuration

| Environment variable | Default | Purpose / 用途 |
|---|---:|---|
| `IBKR_HOST` | `127.0.0.1` | TWS host / TWS 地址 |
| `IBKR_PORT` | `7497` | Paper Trading API port / 模拟账户 API 端口 |
| `IBKR_CLIENT_ID` | `2` | API client ID / 客户端编号 |
| `DEFAULT_SYMBOL` | `NVDA` | Default stock symbol / 默认股票代码 |
| `DEFAULT_DURATION` | `1 Y` | Historical duration / 历史范围 |
| `DEFAULT_BAR_SIZE` | `1 day` | Bar size / K 线粒度 |

可参考 `.env.example`。Python 不会自动加载 `.env`；请通过 VS Code、PowerShell 或操作系统设置环境变量，且不要提交凭据。

See `.env.example` for reference. Python does not load it automatically; provide variables through VS Code, PowerShell, or the operating system, and never commit credentials.

## 运行管道 / Run the Pipeline

启动并登录 TWS Paper Trading、启用 API 后运行：

Start and sign in to TWS Paper Trading, enable API access, then run:

```powershell
python -u main.py
```

当前正式支持 `1 day → 1d` 文件名映射，例如：

The currently supported filename mapping is `1 day → 1d`, for example:

```text
data/raw/NVDA_1d.csv
data/processed/NVDA_1d.csv
```

## 离线测试 / Offline Tests

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -p no:cacheprovider -v
```

测试使用内存对象和 pytest 临时目录，不连接真实 TWS，也不会污染项目数据目录。

Tests use in-memory objects and pytest temporary directories. They do not connect to a real TWS session or write into the project data directories.

## 股票研究层 / Stock Research Layer

### 中文

Phase 3B 在稳定的 processed OHLCV schema 上建立了独立 `research` 层；Phase 3C 进一步加入日期化收益、多资产对齐、回撤、滚动指标、基准比较和相关性分析。研究函数只接收内存中的 DataFrame 或 Series，不连接 IBKR、不读取固定路径，也不保存文件。

```python
from research import (
    align_return_series,
    calculate_dated_simple_returns,
    calculate_drawdowns,
    calculate_rolling_annualized_volatility,
    compare_cumulative_performance,
)

asset_returns = calculate_dated_simple_returns(processed_history, "NVDA")
benchmark_returns = calculate_dated_simple_returns(benchmark_history, "SPY")
aligned = align_return_series({"NVDA": asset_returns, "SPY": benchmark_returns})
drawdowns = calculate_drawdowns(asset_returns)
rolling_volatility = calculate_rolling_annualized_volatility(asset_returns, 20)
cumulative_comparison = compare_cumulative_performance(
    asset_returns, benchmark_returns, "NVDA", "SPY"
)
```

核心定义：simple return 为相邻 close 的百分比变化；累计收益和滚动收益使用 `prod(1 + r) - 1` 复利；年化波动率和 rolling annualized volatility 使用样本标准差 `ddof=1` 乘以 `sqrt(periods_per_year)`；wealth index 为初始财富乘以累计增长因子；drawdown 为 wealth 相对 running peak 的比例下降，maximum drawdown 为该序列最小值；active return 为 asset return 减 benchmark return；tracking error 为 active return 样本标准差的年化值；correlation 使用全部资产共同日期样本上的 Pearson correlation。

日期化研究当前要求无时区、唯一且升序的 `DatetimeIndex`。多资产与 benchmark 采用精确日期交集，不填充缺失收益，也不把缺失收益视为零。当前计算仍基于可用 raw close；项目尚未处理 adjusted close、拆股或分红，因此结果是 price return，不一定是 total return。

### English

Phase 3B established an independent `research` layer on the stable processed OHLCV schema. Phase 3C adds date-aware returns, multi-asset alignment, drawdowns, rolling metrics, benchmark comparison, and correlation. Research functions consume in-memory DataFrames or Series only; they do not connect to IBKR, load fixed paths, or save files.

Core definitions: simple return is the percentage change between adjacent closes; cumulative and rolling returns use `prod(1 + r) - 1`; annualized and rolling annualized volatility use sample standard deviation with `ddof=1` multiplied by `sqrt(periods_per_year)`; wealth index compounds growth from an initial value; drawdown measures wealth relative to its running peak and maximum drawdown is its minimum; active return is asset return minus benchmark return; tracking error is the annualized sample standard deviation of active returns; correlation is Pearson correlation over one common date sample shared by all assets.

Date-aware research currently requires a timezone-naive, unique, ascending `DatetimeIndex`. Assets and benchmarks use their exact date intersection without filling missing returns or treating them as zero. Calculations still use the available raw close. Adjusted close, splits, and dividends are not handled, so results are price returns and not necessarily total returns. Options, Greeks, and advanced portfolio risk remain future capabilities.

## Signal 与 Strategy Foundation / Signal and Strategy Foundation

Phase 3D keeps trailing indicators in `research` and activates a separate `strategies` package for market-state signals and target-position intent. The reference moving-average crossover consumes only an in-memory processed OHLCV `DataFrame`:

```python
from strategies import MovingAverageCrossoverStrategy

strategy = MovingAverageCrossoverStrategy(fast_window=20, slow_window=50)
signals = strategy.generate_signals(processed_history)
intents = strategy.generate_intents(processed_history)
```

`fast MA > slow MA` maps to target position `1.0` (long); `fast MA <= slow MA` maps to `0.0` (flat). Before the complete slow window exists, signal state is explicitly `unavailable` and target position is `NaN`. Rolling windows use only current and earlier observations: there is no backward fill or future-data access.

Signal describes an observed market condition. Strategy converts that state into desired exposure. It never submits orders, reads broker positions, manages cash, or assumes fills; backtest, portfolio, risk, and future execution layers consume the intent contract separately.

## Trading Domain 与 Backtest / Trading Domain and Backtest

Phase 3E converts Phase 3D strategy output into a broker-neutral trading flow:

```text
TargetExposureIntent
  → FixedQuantitySizing
  → TargetQuantity
  → Position Reconciliation
  → OrderRequest
  → Next-Open Simulated Execution
  → Fill
  → PortfolioState
  → End-of-Day PortfolioSnapshot
```

`target_position` is interpreted only as standardized target exposure: `1.0` means desired long state and `0.0` means desired flat state. It never directly means one share, account NAV allocation, notional, or a fixed dollar amount. The independent sizing policy converts exposure into quantity; the first implementation is deterministic `FixedQuantitySizing`.

Daily lifecycle is explicit: after Day T closes, the completed bar produces an intent and pending order; at Day T+1 open, that pending order may fill; at Day T+1 close, the portfolio is marked and snapshotted before the next intent is generated. Same-close fills are prohibited.

Domain accounting stores cash, fill prices, commissions, and equity as `Decimal`; research and OHLCV stay `float64`, while `BacktestResult.equity_curve()` provides a numeric pandas view. Orders are broker-neutral records only. This phase does not connect to the IBKR order API or perform Paper/Live Trading.

## Pre-Trade Risk / 交易前风险

Phase 3F adds a broker-neutral, deterministic risk boundary between a pending `OrderRequest` and simulated execution. Explicitly configured rules can restrict allowed `InstrumentId` values, order quantity, resulting long-only position quantity, and equity order notional. Risk evaluation never mutates `PortfolioState`, creates a `Fill`, or grants broker-submission authority.

`BacktestEngine` keeps Phase 3E compatibility: when `risk_configuration` is `None`, the risk layer is disabled. Once risk evaluation is enabled, it is fail-closed and runs at the available T+1 OPEN before simulation; notional uses that OPEN valuation. A final-bar order with no T+1 OPEN receives `ExecutionRejectionReason.NO_NEXT_BAR` directly and is not risk-evaluated, so the number of orders can exceed the number of risk decisions.

Phase 3F 在 pending `OrderRequest` 与模拟执行之间增加 broker-neutral、确定性的风险边界。显式配置的规则可以限制允许的 `InstrumentId`、订单数量、long-only resulting position quantity 和股票订单 notional。风险评估不修改 `PortfolioState`、不创建 `Fill`，也不授予 broker 提交权限。

为保持 Phase 3E 兼容，`risk_configuration=None` 明确表示 risk layer 未启用；一旦启用，评估严格 fail-closed，并在存在真实 T+1 OPEN 时、simulation 之前运行。最后一根 bar 产生但没有下一 OPEN 的订单直接记录 `NO_NEXT_BAR`，不产生 `RiskDecision`，因此 orders 数量不保证等于 risk decisions 数量。

## Execution Lifecycle / 执行生命周期

Phase 3G adds a broker-neutral `execution` boundary after planning and risk. A stable `ClientOrderId` identifies one logical execution; an explicit `SubmissionAuthorization` is required before the immutable order can enter `SUBMISSION_PENDING`. This state must be saved before any future broker side effect. `UNKNOWN` means delivery to the broker cannot be determined and therefore blocks resubmission until reconciliation or operator resolution. Broker identities and execution-fill identities remain separate from local identity, while `ExecutionFill` associates provenance with the unchanged economic `trading.Fill`.

Phase 3G 在 planning 和 risk 之后增加 broker-neutral `execution` 边界。稳定的 `ClientOrderId` 标识一个逻辑执行；immutable order 必须获得独立 `SubmissionAuthorization` 才能进入 `SUBMISSION_PENDING`，且该状态必须在未来任何 broker 副作用之前保存。`UNKNOWN` 表示无法判断 broker 是否收到请求，因此在 reconciliation 或人工处置前禁止重新提交。Broker identity、execution-fill identity 与本地 identity 保持分离，`ExecutionFill` 为未改变的 economic `trading.Fill` 关联执行来源。

```text
strategy → planning → risk → authorization → execution lifecycle
                                                ↓
                              IBKR Paper adapter foundation
```

The included repository is deliberately in-memory and provides no crash or restart durability. Phase 3G does not connect to IBKR and provides no `placeOrder`, `cancelOrder`, Paper runner, persistent repository, automatic retry, or Live Trading capability.

当前 repository 仅为内存实现，不提供 crash 或 restart durability。Phase 3G 不连接 IBKR，也不提供 `placeOrder`、`cancelOrder`、Paper runner、持久化 repository、自动重试或 Live Trading 能力。

## Phase 3H — IBKR Paper Execution Adapter Foundation

中文：发送遵循 prepare → revalidate → claim → side effect；准备失败不消费 claim 或 broker order ID。旧 reconciliation API 的 broker 累计数量也仅作比较证据，经济累计只由接受的 ExecutionFill 推进。UNKNOWN 保留已知事实；CANCELLED 表示剩余未成交部分取消，不意味着从未成交。

English: Dispatch follows prepare → revalidate → claim → side effect; failed preparation consumes neither claim nor broker order ID. Broker cumulative quantities, including the legacy reconciliation API, are comparison evidence only; accepted ExecutionFill records alone advance economic totals. UNKNOWN preserves known facts. CANCELLED cancels the unfilled remainder and does not imply zero fills.

中文：`broker/ibkr/` 已建立单一美股 MKT 映射、独立身份、提交/撤单边界、原始 callback 归一化、错误分类和 execution/commission 配对。`execution/` 提供进程内一次性 claim 及显式异步观察规则。broker Filled 不增加经济数量；只有费用完整的 ExecutionFill 可入账。关键实现提供中英文 docstring 与安全原因说明。

English: `broker/ibkr/` provides single-US-equity MKT mapping, separate identities, submit/cancel boundaries, raw callback normalization, error translation and execution/commission pairing. `execution/` adds process-lifetime claims and explicit asynchronous observation rules. Broker Filled does not increase economic quantity; only fee-complete ExecutionFill records can be booked. Critical APIs and safety rationale are bilingual.

**中文：真实订单 transport 始终锁闭；默认配置 DISABLED。3H 内存 claim 没有 crash durability；3I 的 SQLite 替代实现及最小离线 runner 见下文。人工审批 workflow、周期及组合 reconciliation、自动重试、Live Trading 和期权执行均未实现。项目不能无人值守自动交易。**

**English: Real order transport remains unconditionally locked; configuration defaults to DISABLED. The 3H memory claims have no crash durability; see the 3I SQLite alternative and minimal offline runner below. Approval workflows, periodic/portfolio reconciliation, automatic retry, live trading and options execution remain unimplemented. This project is not ready for unattended trading.**

只读 integration smoke 默认跳过；本阶段不以实际下单验收。 Read-only integration smoke is skipped by default; real orders are not an acceptance requirement. 详见 / See [IBKR execution architecture and limitations](docs/ibkr_execution.md).

## Phase 3I — Paper Trading Runner & Recovery Foundation

中文：基线 v0.10 / Phase 3H 已合并（`d73308d` → PR #9 `6319e98`）。3I 已通过 PR #10 合并，merge commit `574d1a5`；不宣称已发布新版本。标准库 SQLite 保存 execution aggregate、一次性 claim、成交去重、原始 callback 和记账标记。金额精确使用 Decimal；订单与成交身份同事务提交；记账缺口可在重启后显式补齐且不会重复扣款。恢复清单和纯 reconciliation 比较不会自动重发 UNKNOWN。薄 `application.PaperRunner` 只编排显式调用，阻止存在未完成执行、未决证据或记账缺口时的新规划。

English: The baseline is v0.10 / merged Phase 3H (`d73308d` → PR #9 `6319e98`). Phase 3I is merged through PR #10 (`574d1a5`), without a new version release. Standard-library SQLite stores aggregates, one-shot claims, fill identities, raw callbacks and accounting markers. Decimal values remain exact; execution state and fill dedup commit together. Restart can explicitly complete an accounting gap without double booking. Recovery listings and pure reconciliation comparisons never resend UNKNOWN. The thin `application.PaperRunner` orchestrates explicit calls and blocks new planning while executions, unresolved evidence or accounting gaps remain.

中文：这仍不是 autonomous live trading system。real-money trading、automatic UNKNOWN retry、full reconciliation loop、distributed execution、multi-process coordination、production HA 均不支持；Paper transport 仍 locked。在线只读 integration 尚无正式验收证据。与已接受成交匹配的佣金等待可定向解除并保留审计；其他未决证据保守保留，没有通用清除或人工审批 UI；详见 [持久化与恢复边界](docs/execution_recovery.md)。

English: This is not an autonomous live trading system. Real-money trading, automatic UNKNOWN retry, a full reconciliation loop, distributed execution, multi-process coordination and production HA are unsupported; Paper transport remains locked. Online read-only integration has no formal acceptance evidence. Commission waits matching accepted fills are resolved with audit retention; other uncertainty is conservatively retained without blanket clearing or an approval UI. See [persistence and recovery boundaries](docs/execution_recovery.md).

## 安全边界 / Safety Boundary

### 中文

项目当前真实 IBKR 通道只允许显式只读访问，订单 transport 锁闭。端口和 readonly 参数不是 Paper 证明；查询连接也必须核对配置与账户。Paper Trading 自动执行和 Live Trading 都必须经过独立设计、安全审查与明确人工批准。

### English

Real IBKR access remains explicitly read-only and order transport is locked. Neither a port nor the readonly argument proves Paper safety; the dedicated observation session validates configuration and accounts. Automated paper execution and live trading require separate design, safety review, and explicit human approval.

中文：3I 安全修复采用一次性 PlanningTicket 绑定组合 revision、计划和风险决策；SQLite v2 强制 broker identity 唯一归属、跨会话 correction-family 拒绝，并以固定 Decimal context 重建组合。修复已随 Phase 3I 合并。
English: The 3I pre-commit fixes bind a one-use PlanningTicket to portfolio revision, plan and risk decision. SQLite v2 enforces broker ownership and cross-session correction-family rejection; accounting uses a fixed Decimal context. These fixes are merged with Phase 3I.


## Phase 3J — IBKR Paper Execution & Reconciliation Foundation

中文：本地 feature branch 开发，未提交。增加显式只读 session、raw broker observation mapping、强身份 outstanding-order reconciliation 和 durable results。CONNECTED 不等于 READY；READY 不授予发送权限。MATCHED/BROKER_ONLY/LOCAL_ONLY/CONFLICT/UNKNOWN 均为证据判断，不自动修改订单、成交或持仓。未知、缺失和冲突保守阻断；没有自动 resend/retry。真实 place/cancel 仍锁闭，项目仍不是 live 或无人值守 Paper Trading system。版本保持 v0.10。

English: Phase 3J adds explicit read-only sessions, neutral broker observations, strong-identity outstanding-order reconciliation and durable results. It is locally implemented and uncommitted. Connectivity is distinct from readiness; observations never authorize arbitrary local mutations. Real place/cancel remain locked, with no automatic resend, retry or background trading loop. See [IBKR reconciliation architecture and limits](docs/ibkr_reconciliation.md).
