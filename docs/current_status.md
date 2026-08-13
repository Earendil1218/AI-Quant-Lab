# 当前项目状态

最后更新：2026-08-14

## 当前里程碑

- 版本：AI-Quant-Lab v0.2
- Roadmap 阶段：Phase 1 — 工程基础与 IBKR 只读数据连接
- 状态：已完成，等待确认并开始 Phase 2

## Completed

- 建立集中配置模块，支持环境变量和开发默认值
- 将 IBKR TWS 只读连接独立为 broker 连接模块
- 将股票合约、历史数据请求和 DataFrame 转换独立为市场数据模块
- 建立仅负责流程编排的 `main.py`
- 建立 `data/raw/` 和 `data/processed/` 目录骨架，尚未自动保存行情
- 建立不依赖真实 TWS 的基础测试
- 建立最小依赖清单，并完善 README 与 Git 忽略规则
- 移除已被正式模块替代的测试脚本

## Verified

### 离线验证

- 6 项 `unittest` 测试全部通过
- 配置类型、核心函数存在性和函数签名已验证
- 历史数据请求参数、DataFrame 转换和空数据处理已验证
- 测试使用内存假对象，不连接真实 TWS
- 未发现订单提交、修改、撤销或期权行权逻辑

### IBKR Paper Trading 在线验证

2026-08-13 在 VS Code Terminal 中人工执行：

```powershell
python -u main.py
```

结果：

- 成功连接 IBKR TWS Paper Trading
- 成功获取 NVDA 一年日线历史数据，共 251 条
- 日期范围：2025-08-14 至 2026-08-13
- 成功输出最近 5 条数据
- 程序正常断开 TWS 连接

## In Progress

暂无。下一阶段尚未开始，等待 Phase 2 方案确认。

## Known Issues

- Codex 自动执行环境中，在线运行曾分别在 30 秒和 45 秒达到工具超时；同一程序已由用户在 VS Code Terminal 中人工验证成功，因此当前判断为自动执行环境问题，而非代码功能失败。
- 当前测试覆盖基础接口、正常历史数据转换和空数据分支，尚未覆盖连接失败、contract qualify 失败及其他 IBKR 异常返回。

## Next

1. 明确历史数据文件格式、命名规则、目录边界和更新时间规则。
2. 设计独立、简单的数据存储层，保持 broker 模块不负责持久化。
3. 为连接失败、contract qualify 失败和异常返回增加离线测试。
4. 实现并验证历史数据的本地保存与更新流程。
5. 存储流程稳定后，进入数据清洗和股票研究。

当前安全限制保持不变：仅使用 IBKR Paper Trading 和只读历史数据访问，不包含订单功能。
