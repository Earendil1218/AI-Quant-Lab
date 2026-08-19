# 当前项目状态 / Current Project Status

最后更新 / Last updated: 2026-08-19

## 当前里程碑 / Current Milestone

### 中文

- 版本：AI Quant Lab v0.5
- Roadmap：Phase 3B — Stock Research Foundation
- 状态：实现完成，等待最终验收

### English

- Version: AI Quant Lab v0.5
- Roadmap: Phase 3B — Stock Research Foundation
- Status: implementation complete, pending final acceptance

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

## 已验证 / Verified

### 中文

- 90 项 pytest 离线测试全部通过，无失败或 warning。
- processing、validation、raw/processed path 和 CSV round-trip 均由固定输入或 pytest 临时目录验证。
- 测试不连接真实 TWS，不写入项目数据目录，也不调用订单接口。
- Phase 2 曾由用户人工在线验证：成功获取、验证、保存并重载 251 条 NVDA 日线数据。
- Phase 3A 于 2026-08-19 由用户人工在线验证：251 条 NVDA 日线完成 raw 保存、processed 保存、重载验证并正常断开 TWS。

### English

- All 90 offline pytest tests pass with no failures or warnings.
- Processing, validation, raw/processed paths, and CSV round trips use deterministic inputs or pytest temporary directories.
- Tests do not connect to TWS, write to project data directories, or invoke order APIs.
- Phase 2 was previously verified manually online with 251 NVDA daily bars fetched, validated, saved, and reloaded.
- Phase 3A was manually verified online on 2026-08-19: 251 NVDA daily bars completed raw storage, processed storage, reload validation, and a clean TWS disconnect.

## Phase 3B / Stock Research Foundation

### 中文

- 新增独立 `research` package，与 processing、storage 和 broker 解耦。
- 支持 simple return、log return 和复利 cumulative return，并保留首项 NaN。
- 支持观察数、均值、样本标准差、最小值、最大值、累计收益、几何年化收益和年化波动率。
- 日线默认使用 `TRADING_DAYS_PER_YEAR = 252`；这是可覆盖的市场惯例假设。
- 所有 public API 使用中英双语 docstring，计算可完全离线运行。

### English

- Added an independent `research` package decoupled from processing, storage, and broker access.
- Added simple, log, and compounded cumulative returns while preserving the leading NaN.
- Added count, mean, sample standard deviation, minimum, maximum, cumulative return, geometric annualized return, and annualized volatility.
- Daily calculations default to `TRADING_DAYS_PER_YEAR = 252`, an overridable market-convention assumption.
- All public APIs have bilingual docstrings and run fully offline.

## 已知限制 / Known Limitations

### 中文

- 当前仅正式支持 `1 day → 1d` 文件名映射。
- CSV 保存仍是同名文件全量覆盖，尚未实现增量合并。
- 日线 date 必须不含时区；分钟线和多时区策略尚未设计。
- 尚未处理拆股、分红或 adjusted price。
- 连接失败、contract qualify 失败和部分 IBKR 异常返回仍缺少离线测试。

### English

- Only the `1 day → 1d` filename mapping is formally supported.
- CSV persistence still replaces the complete file; incremental merging is not implemented.
- Daily dates must be timezone-naive; intraday and multi-timezone policies are not yet designed.
- Splits, dividends, and adjusted prices are not handled.
- Connection failures, contract qualification failures, and some IBKR error responses still lack offline tests.

## 下一步 / Next

1. 人工审阅并验收 Phase 3B research API、数学定义和文档。
2. 验收后单独执行 Git commit、push 和 PR 工作流。
3. 在明确覆盖、重叠和来源优先级规则后单独设计增量更新。

1. Manually review and accept the Phase 3B research APIs, financial definitions, and documentation.
2. Run the Git commit, push, and PR workflow separately after acceptance.
3. Design incremental updates separately after overlap and source-priority rules are explicit.

当前安全限制保持不变：只允许只读市场数据访问，不包含订单或自动执行。

The safety boundary is unchanged: only read-only market-data access is allowed, with no order or automated execution capability.
