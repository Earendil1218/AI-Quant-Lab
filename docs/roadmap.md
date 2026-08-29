# AI-Quant-Lab 路线图

本路线图描述项目的长期开发顺序和阶段完成标准。项目当前所处阶段、最近验证结果和下一项具体任务见 `current_status.md`。

## 阶段依赖

```text
开发环境与项目初始化
        ↓
工程基础与 IBKR 只读数据连接
        ↓
历史数据存储与更新
        ↓
数据清洗与股票研究
        ↓
期权数据
        ↓
期权定价、IV 与 Greeks
        ↓
策略研究
        ↓
回测
        ↓
风险管理
        ↓
AI 辅助研究
        ↓
Paper Trading 策略执行
        ↓
Live Trading 研究（严格审批）
```

## Phase 0：开发环境与项目初始化

目标：建立稳定、可追踪的本地开发基础。

主要能力：

- Python 3.11 与虚拟环境
- VS Code、Git、GitHub 和 Codex
- 基础项目目录与项目文档

完成标准：项目可以在版本控制下进行可重复的本地开发。

## Phase 1：工程基础与 IBKR 只读数据连接

目标：建立职责清晰的 Python 工程结构，并验证 IBKR 历史数据链路。

主要能力：

- 集中配置
- IBKR TWS Paper Trading 只读连接
- 股票历史数据请求与 DataFrame 转换
- 主程序编排
- 不依赖真实 TWS 的基础测试

前置依赖：Phase 0。

完成标准：模块边界清晰，离线测试通过，并能从 Paper Trading 获取 NVDA 历史日线后正常断开。

## Phase 2：历史数据存储基础 / Historical Data Storage Foundation

目标：可靠地保存、读取和验证原始历史市场数据。

Goal: reliably persist, reload, and validate raw historical market data.

主要能力：

- 文件格式和命名规范
- 原始数据与处理后数据的目录边界
- 本地保存与读取流程
- 重复数据、时间顺序与日期范围验证
- 基础数据完整性验证

前置依赖：Phase 1。

完成标准：可以保存和重新加载规范命名的 raw CSV，并验证重载结果。增量合并保留为后续独立能力。

Completion: canonically named raw CSV data can be saved, reloaded, and validated. Incremental merging remains a separate future capability.

## Phase 3：Processed 数据与股票研究 / Processed Data and Stock Research

目标：先建立可靠的 processed market data 边界，再在其上发展股票研究能力。

Goal: establish a reliable processed-market-data boundary before building stock-research capabilities on top of it.

### Phase 3A：Processed Market Data Pipeline

- datetime、OHLCV dtype、列顺序、时间顺序和 index 标准化
- raw 与 processed 存储分层
- 重复 timestamp 明确报错，不静默删除
- 离线测试覆盖 processing、validation 和 processed CSV round-trip

完成标准：可以从 raw DataFrame 生成并重载具有稳定 schema 的 processed CSV。当前已实现。

Completion: a raw DataFrame can be transformed into and reloaded from a processed CSV with a stable schema. This subphase is implemented.

状态 / Status：已完成 / Completed.

### Phase 3B：Stock Research Foundation

主要能力：

- 收益率及基础统计指标
- 可复用的股票研究流程

前置依赖：Phase 2。

完成标准：研究计算有测试支撑，并能在 processed schema 上产生可复现结果。

Completion: research calculations are tested and reproducible on the processed schema.

状态：已实现。当前包括 simple return、log return、复利累计收益、基础描述统计、几何年化收益和日线年化波动率；策略、回测和 performance analytics 仍属于后续阶段。

Status: implemented. The current scope includes simple returns, log returns, compounded cumulative returns, basic descriptive statistics, geometric annualized return, and daily annualized volatility. Strategy, backtesting, and performance analytics remain future phases.

状态 / Status：已完成并合并 / Completed and merged.

### Phase 3C：Performance and Comparative Research Foundation

主要能力：

- 日期化 simple-return Series 与多资产精确日期交集对齐
- wealth index、drawdown、maximum drawdown 与 peak/trough/recovery 日期
- 完整窗口 rolling compounded return 与 rolling annualized volatility
- benchmark 累计表现比较、active return 与 annualized tracking error
- 使用统一共同日期样本的 Pearson correlation matrix

Core capabilities:

- Date-aware simple-return Series and exact-date multi-asset alignment
- Wealth index, drawdown, maximum drawdown, and peak/trough/recovery dates
- Complete-window rolling compounded return and rolling annualized volatility
- Benchmark cumulative comparison, active returns, and annualized tracking error
- Pearson correlation matrices over one shared common-date sample

完成标准：公共 API 定义明确，金融语义由确定性离线测试锁定，不连接 broker 或执行文件 I/O。

Completion: public APIs have explicit definitions, deterministic offline tests lock their financial semantics, and no broker connection or file I/O occurs.

状态 / Status：已完成 / Completed.

### Phase 3D：Signal and Strategy Foundation

主要能力：

- trailing simple moving average research indicator
- 显式 signal state 与可选 numeric value
- broker-independent Strategy abstraction 与 date-indexed target-position intent
- 可配置的 moving-average crossover reference strategy
- 完整窗口 warm-up 和 look-ahead protection

完成标准：processed OHLCV 可以纯内存地产生确定性 signal 和 long/flat target position；未来数据变更不改变历史输出；不连接 broker、storage 或 execution。

Completion: processed OHLCV produces deterministic in-memory signals and long/flat target positions; future-data changes cannot alter historical outputs; broker, storage, and execution remain outside this layer.

状态 / Status：已完成并合并 / Completed and merged.

### Phase 3E：Trading Domain and Backtest Foundation

主要能力：

- broker-neutral instrument、target intent、order、fill contracts
- target exposure 与 target quantity 分离，第一版使用 fixed-quantity sizing
- cash、position quantity、mark-to-market 与 end-of-day portfolio snapshots
- planning decision 与 execution rejection 分层
- T close decision → T+1 open simulated execution
- deterministic fixed commission、basis-point slippage 与 numeric equity-curve view

Core capabilities:

- Broker-neutral instrument, target-intent, order, and fill contracts
- Separate target exposure and target quantity with fixed-quantity sizing first
- Cash, position quantity, mark-to-market, and end-of-day portfolio snapshots
- Separate planning decisions and execution rejections
- T-close decisions followed by T+1-open simulated execution
- Deterministic fixed commission, basis-point slippage, and a numeric equity-curve view

完成标准：single-equity daily long/flat strategy 可以从 Phase 3D intent 经 sizing、position reconciliation、broker-neutral order、simulated fill 和 accounting 产生确定性的 orders、fills、cash、position 与 equity curve；核心 trading domain 不依赖 pandas、IBKR 或 ib_insync。

Completion: a single-equity daily long/flat strategy produces deterministic orders, fills, cash, positions, and an equity curve from Phase 3D intent through sizing, reconciliation, broker-neutral orders, simulated fills, and accounting. The core trading domain does not depend on pandas, IBKR, or ib_insync.

状态 / Status：已实现，等待 feature branch 验收 / Implemented, pending feature-branch acceptance.

## Phase 4：期权数据

目标：建立期权合约与期权市场数据的获取和标准化能力。

主要能力：

- 期权链与合约筛选
- 到期日、执行价和看涨/看跌类型处理
- Bid、Ask、Last、成交量和未平仓量
- 标的价格、利率和到期时间等定价输入

前置依赖：Phase 1；存储复用 Phase 2 的原则。

完成标准：能够稳定获取并标准化研究所需的期权数据，且不包含订单操作。

## Phase 5：期权定价、IV 与 Greeks

目标：建立可验证的期权定价分析能力。

主要能力：

- Black-Scholes 模型
- 隐含波动率计算
- Delta、Gamma、Theta、Vega 等 Greeks
- 边界条件和数值结果测试

前置依赖：Phase 4。

完成标准：核心计算具有单元测试，并可与可信参考结果交叉验证。

## Phase 6：策略研究

目标：用明确、可复用的数据结构表达策略及其假设。

主要能力可包括：

- Covered Call
- Cash Secured Put
- Bull Call Spread 与 Bear Put Spread
- Iron Condor
- Calendar Spread

前置依赖：Phase 3；期权策略还依赖 Phase 5。

完成标准：策略输入、规则、成本假设和预期风险收益均可明确表达，不直接提交订单。

## Phase 7：回测

目标：使用历史数据评估策略表现和局限。

主要能力：

- 历史数据回放
- 交易成本与滑点假设
- 盈亏曲线
- Sharpe Ratio、最大回撤、胜率等指标
- 防止前视偏差和数据泄漏的检查

前置依赖：Phase 2、Phase 3 和 Phase 6。

完成标准：回测结果可复现，关键假设透明，并具有基础正确性测试。

## Phase 8：风险管理

目标：建立独立于具体策略的风险度量和限制体系。

主要能力：

- 仓位和集中度度量
- 最大亏损与回撤限制
- 股票及期权风险暴露
- 策略级和组合级风险检查

前置依赖：Phase 6 和 Phase 7。

完成标准：风险规则可独立测试，并能在任何执行能力之前拦截不合规意图。

## Phase 9：AI 辅助研究

目标：让 AI 提升研究效率，同时保持结果可验证、决策可追溯。

主要能力：

- 辅助市场与数据分析
- 辅助生成研究假设和策略候选
- 自动组织回测与结果比较
- 对 AI 输出进行确定性验证和人工复核

前置依赖：相关数据、策略、回测和风险模块已稳定。

完成标准：AI 不绕过测试、安全限制或人工审批，输出可以被复核和复现。

## Phase 10：Paper Trading 策略执行

目标：在模拟账户中验证从信号到执行的完整流程。

主要能力：

- 独立订单模型和执行接口
- 订单前风险检查
- 幂等、状态同步和审计记录
- 紧急停止与人工确认机制
- Paper Trading 端到端测试

前置依赖：Phase 7 和 Phase 8，并需单独设计和批准。

完成标准：所有执行仅限模拟账户，失败模式经过测试，且每项订单能力都有明确安全控制。

## Phase 11：Live Trading 研究

目标：仅在前序能力长期稳定后，评估真实交易所需的额外控制和合规要求。

可能涉及：

- 更严格的账户、权限和环境隔离
- 多层人工审批
- 监控、告警、审计和故障恢复
- 小规模、可撤销的上线方案

前置依赖：Phase 10 已充分验证，并获得用户针对 Live Trading 的明确专项授权。

完成标准：此阶段的具体标准必须在进入前重新设计和审批。路线图中列出该阶段不构成任何真实交易授权。
