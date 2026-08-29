# 当前项目状态 / Current Project Status

最后更新 / Last updated: 2026-08-29

## 当前里程碑 / Current Milestone

### 中文

- 版本：AI Quant Lab v0.8
- Roadmap：Phase 3E — Trading Domain and Backtest Foundation
- 状态：Phase 3A–3E 已完成并合并到 `main`

### English

- Version: AI Quant Lab v0.8
- Roadmap: Phase 3E — Trading Domain and Backtest Foundation
- Status: Phases 3A–3E are completed and merged into `main`

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

## 已验证 / Verified

### 中文

- 268 项 pytest 离线测试全部通过，无失败或 warning。
- processing、validation、raw/processed path 和 CSV round-trip 均由固定输入或 pytest 临时目录验证。
- 测试不连接真实 TWS，不写入项目数据目录，也不调用订单接口。
- Phase 2 曾由用户人工在线验证：成功获取、验证、保存并重载 251 条 NVDA 日线数据。
- Phase 3A 于 2026-08-19 由用户人工在线验证：251 条 NVDA 日线完成 raw 保存、processed 保存、重载验证并正常断开 TWS。

### English

- All 268 offline pytest tests pass with no failures or warnings.
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

## 已知限制 / Known Limitations

### 中文

- 当前仅正式支持 `1 day → 1d` 文件名映射。
- CSV 保存仍是同名文件全量覆盖，尚未实现增量合并。
- 日线 date 必须不含时区；分钟线和多时区策略尚未设计。
- 尚未处理拆股、分红或 adjusted price。
- 尚未设计多交易所 calendar policy。
- 当前 backtest 仅支持 single-equity、daily、long/flat、fixed quantity、next-open execution；尚未实现 Options、Greeks 或 Portfolio Risk。
- 不支持自动化 Paper Trading 或 Live Trading。
- 连接失败、contract qualify 失败和部分 IBKR 异常返回仍缺少离线测试。

### English

- Only the `1 day → 1d` filename mapping is formally supported.
- CSV persistence still replaces the complete file; incremental merging is not implemented.
- Daily dates must be timezone-naive; intraday and multi-timezone policies are not yet designed.
- Splits, dividends, and adjusted prices are not handled.
- No multi-exchange calendar policy has been designed.
- Backtesting is limited to single-equity, daily, long/flat, fixed-quantity, next-open execution; options, Greeks, and portfolio risk are not implemented.
- Automated paper trading and live trading are not supported.
- Connection failures, contract qualification failures, and some IBKR error responses still lack offline tests.

## 下一步 / Next

1. 评审下一小阶段的 architecture boundary，不自动开始 Phase 3F。
2. 比较 Portfolio Risk 与 broker execution abstraction 的优先级；这不直接授权 Paper order submission。
3. Options、增量更新、分钟线时区和 corporate actions 继续作为独立能力设计。

1. Review the next small phase's architecture boundary without automatically starting Phase 3F.
2. Compare Portfolio Risk and a broker execution abstraction as priorities; this does not authorize Paper order submission.
3. Keep options, incremental updates, intraday timezone semantics, and corporate actions as separate capabilities.

当前安全限制保持不变：broker 只允许只读市场数据访问；broker-neutral 模拟订单不会提交到 IBKR，不包含自动执行。

The safety boundary is unchanged: broker access remains read-only; broker-neutral simulated orders are never submitted to IBKR and no automated execution is included.
