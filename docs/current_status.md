# 当前项目状态 / Current Project Status

最后更新 / Last updated: 2026-08-17

## 当前里程碑 / Current Milestone

### 中文

- 版本：AI Quant Lab v0.4
- Roadmap：Phase 3A — Processed Market Data Pipeline
- 状态：实现完成，等待最终离线验证和人工在线验证

### English

- Version: AI Quant Lab v0.4
- Roadmap: Phase 3A — Processed Market Data Pipeline
- Status: implementation complete, pending final offline verification and manual online verification

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

- 65 项 pytest 离线测试全部通过，无失败或 warning。
- processing、validation、raw/processed path 和 CSV round-trip 均由固定输入或 pytest 临时目录验证。
- 测试不连接真实 TWS，不写入项目数据目录，也不调用订单接口。
- Phase 2 曾由用户人工在线验证：成功获取、验证、保存并重载 251 条 NVDA 日线数据。

### English

- All 65 offline pytest tests pass with no failures or warnings.
- Processing, validation, raw/processed paths, and CSV round trips use deterministic inputs or pytest temporary directories.
- Tests do not connect to TWS, write to project data directories, or invoke order APIs.
- Phase 2 was previously verified manually online with 251 NVDA daily bars fetched, validated, saved, and reloaded.

## 已知限制 / Known Limitations

### 中文

- Phase 3 完整在线管道尚未在用户的 TWS 会话中人工验证。
- 当前仅正式支持 `1 day → 1d` 文件名映射。
- CSV 保存仍是同名文件全量覆盖，尚未实现增量合并。
- 日线 date 必须不含时区；分钟线和多时区策略尚未设计。
- 尚未处理拆股、分红或 adjusted price。
- 连接失败、contract qualify 失败和部分 IBKR 异常返回仍缺少离线测试。

### English

- The complete Phase 3 online pipeline has not yet been manually verified in the user's TWS session.
- Only the `1 day → 1d` filename mapping is formally supported.
- CSV persistence still replaces the complete file; incremental merging is not implemented.
- Daily dates must be timezone-naive; intraday and multi-timezone policies are not yet designed.
- Splits, dividends, and adjusted prices are not handled.
- Connection failures, contract qualification failures, and some IBKR error responses still lack offline tests.

## 下一步 / Next

1. 在 VS Code Terminal 中人工运行 `python -u main.py`，确认 raw 和 processed CSV 均正确生成。
2. 在稳定 processed schema 上开始 Phase 3B 股票研究基础，包括收益率和基础统计，但不进入策略或回测。
3. 在明确覆盖、重叠和来源优先级规则后单独设计增量更新。

1. Run `python -u main.py` manually in the VS Code terminal and verify both raw and processed CSV output.
2. Begin Phase 3B stock-research foundations on the stable processed schema without entering strategy or backtesting work.
3. Design incremental updates separately after overlap and source-priority rules are explicit.

当前安全限制保持不变：只允许只读市场数据访问，不包含订单或自动执行。

The safety boundary is unchanged: only read-only market-data access is allowed, with no order or automated execution capability.
