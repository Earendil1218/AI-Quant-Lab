# 当前项目状态 / Current Project Status

最后更新 / Last updated: 2026-08-22

## 当前里程碑 / Current Milestone

### 中文

- 版本：AI Quant Lab v0.6
- Roadmap：Phase 3C — Performance and Comparative Research Foundation
- 状态：Phase 3A、3B 和 3C 已实现；Phase 3C 等待最终 Git 工作流

### English

- Version: AI Quant Lab v0.6
- Roadmap: Phase 3C — Performance and Comparative Research Foundation
- Status: Phases 3A, 3B, and 3C are implemented; Phase 3C awaits the final Git workflow

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

## 已验证 / Verified

### 中文

- 185 项 pytest 离线测试全部通过，无失败或 warning。
- processing、validation、raw/processed path 和 CSV round-trip 均由固定输入或 pytest 临时目录验证。
- 测试不连接真实 TWS，不写入项目数据目录，也不调用订单接口。
- Phase 2 曾由用户人工在线验证：成功获取、验证、保存并重载 251 条 NVDA 日线数据。
- Phase 3A 于 2026-08-19 由用户人工在线验证：251 条 NVDA 日线完成 raw 保存、processed 保存、重载验证并正常断开 TWS。

### English

- All 185 offline pytest tests pass with no failures or warnings.
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

## 已知限制 / Known Limitations

### 中文

- 当前仅正式支持 `1 day → 1d` 文件名映射。
- CSV 保存仍是同名文件全量覆盖，尚未实现增量合并。
- 日线 date 必须不含时区；分钟线和多时区策略尚未设计。
- 尚未处理拆股、分红或 adjusted price。
- 尚未设计多交易所 calendar policy。
- 尚未实现 Strategy、Backtest、Options、Greeks 或 Portfolio Risk。
- 不支持自动化 Paper Trading 或 Live Trading。
- 连接失败、contract qualify 失败和部分 IBKR 异常返回仍缺少离线测试。

### English

- Only the `1 day → 1d` filename mapping is formally supported.
- CSV persistence still replaces the complete file; incremental merging is not implemented.
- Daily dates must be timezone-naive; intraday and multi-timezone policies are not yet designed.
- Splits, dividends, and adjusted prices are not handled.
- No multi-exchange calendar policy has been designed.
- Strategy, backtesting, options, Greeks, and portfolio risk are not implemented.
- Automated paper trading and live trading are not supported.
- Connection failures, contract qualification failures, and some IBKR error responses still lack offline tests.

## 下一步 / Next

1. 完成 Phase 3C 的人工验收和独立 Git commit/push/PR 工作流。
2. 重新评估下一阶段方向：股票 Signal/Strategy Foundation，或 Options Market Data / Pricing / Greeks。
3. 增量更新、分钟线时区和 corporate actions 继续作为独立数据能力设计。

1. Complete Phase 3C acceptance and its separate Git commit/push/PR workflow.
2. Reassess the next direction: a stock Signal/Strategy Foundation or Options Market Data / Pricing / Greeks.
3. Keep incremental updates, intraday timezone semantics, and corporate actions as separate data-capability designs.

当前安全限制保持不变：只允许只读市场数据访问，不包含订单或自动执行。

The safety boundary is unchanged: only read-only market-data access is allowed, with no order or automated execution capability.
