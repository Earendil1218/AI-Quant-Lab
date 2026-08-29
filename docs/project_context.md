# AI-Quant-Lab 项目上下文

## 项目定位

AI-Quant-Lab 是一个个人 AI 辅助量化研究实验室，用于系统学习和实践市场数据、定价、策略、回测与风险管理。

项目的长期目标是建立一套职责清晰、可验证、可逐步扩展并适合国际协作的量化研究平台，而不是尽快搭建自动交易系统。

AI Quant Lab aims to become a clearly layered, verifiable, extensible quantitative research platform suitable for international collaboration—not a shortcut to automated trading.

当前开发状态和近期任务见 `current_status.md`，长期阶段安排见 `roadmap.md`。

## 项目范围

长期研究范围包括：

- 美股市场数据获取、存储、清洗与分析
- 股票和期权研究
- Black-Scholes、隐含波动率与 Greeks
- 策略定义和历史回测
- 风险度量与控制
- IBKR TWS API 集成
- AI 辅助研究、分析和代码开发
- 在具备充分测试与审批机制后研究 Paper Trading 自动化
- 仅在未来满足严格安全条件时研究 Live Trading

各项能力按阶段逐步建设。尚未进入对应阶段的内容不应提前引入当前实现。

## 总体架构

项目按职责分层：

```text
broker market data → data → research → signal → strategy
                                             ↓
                                      target exposure
                                             ↓
trading domain → sizing → portfolio planning → risk (future)
                                             ↓
                                    execution abstraction
                                      ↙             ↘
                              backtest simulation   broker adapter (future)
```

- `config` 管理运行参数，不包含业务流程。
- `broker` 隔离外部券商 API 连接和市场数据访问，不承担数据持久化或策略逻辑。
- `data` 负责市场数据验证、标准化和持久化；raw 与 processed 数据具有明确边界。
- `pricing` 负责定价模型、隐含波动率和 Greeks。
- `strategies` 只表达 signal 和 desired target exposure，不直接拥有券商、账户、现金或订单职责。
- `trading` 定义与 broker 无关的 instrument、intent、order 和 fill 语言。
- `portfolio` 负责 sizing、目标数量 reconciliation、cash/position accounting 和 fill application。
- `backtest` 编排历史 daily event lifecycle 和模拟执行，不依赖 IBKR。
- `risk` 负责风险指标、限制和控制规则。
- 应用入口负责组合各模块，不把底层实现细节重新写入主流程。

上层可以依赖下层提供的稳定接口；底层模块不应反向承担应用编排职责。

## 核心技术栈

- Python 3.11
- VS Code
- Git 与 GitHub
- Codex
- IBKR TWS API 与 `ib-insync`
- pandas

numpy、scipy、matplotlib 等科学计算工具可在实际功能需要时引入。数据库、容器和其他基础设施也应在需求明确后再选择，而不是预先增加。

具体技术选择及原因见 `decisions.md`。

## 核心工程原则

- 单一职责：配置、外部连接、数据访问、存储、研究和流程编排保持边界清晰。
- 简单优先：只实现当前阶段需要的能力，不提前建设复杂框架。
- 小步开发：先计划和确认，再执行有限范围的修改，完成后立即验证。
- 离线测试优先：能使用假对象或固定输入验证的逻辑，不依赖真实 TWS。
- 外部验证分层：离线测试通过后，再按需要进行 Paper Trading 在线验证。
- 配置外置：环境相关参数不散落在业务逻辑中，敏感信息不得提交到 Git。
- 可追溯：重要架构选择写入 `decisions.md`，当前状态写入 `current_status.md`。
- 文档按需更新：普通代码修改通常不更新文档，不为追求形式上的同步制造无意义改动。

## Codex 的角色

Codex 是项目的协作开发助手，可以帮助：

- 阅读和分析现有代码与文档
- 提出分阶段实施方案和风险提示
- 在获得授权后修改代码或文档
- 执行与风险相称的离线测试和只读检查
- 解释工程设计及验证结果

Codex 不应：

- 未经确认扩大任务范围或连续实施未获批准的步骤
- 默认修改所有项目文档
- 未经明确授权执行 Git 暂存、提交或推送
- 未经专项设计、审查和明确审批增加订单或 Live Trading 能力

完成开发任务后，Codex 应先判断变化属于长期上下文、当前状态、路线图、技术决策还是日常工作流，只更新真正需要更新的文档；若均不属于，应明确说明本次修改不需要更新 docs。

## 交易安全边界

项目将以下能力明确分层：

1. **研究与历史数据读取**：当前允许，优先离线测试；在线时仅连接 IBKR Paper Trading。
2. **手工 Paper Trading**：可由用户在 TWS 中独立操作，不等同于授权项目代码提交订单。
3. **自动化 Paper Trading**：未来独立阶段，必须先设计订单、风控、审计、测试和人工审批机制。
4. **Live Trading**：不属于当前实现范围。任何真实账户或订单能力都必须获得用户单独、明确的授权，并经过更严格的安全评审。

除非用户针对具体任务明确授权，否则项目代码不得提交、修改、撤销订单或改变 TWS 交易权限。

## 文档导航

- `project_context.md`：项目是什么、长期范围、架构和原则。
- `roadmap.md`：项目未来按哪些阶段发展。
- `current_status.md`：项目现在做到哪里、已验证什么、下一步是什么。
- `decisions.md`：重要技术和架构选择及其原因。
- `daily_workflow.md`：每天开始、开发和收尾时如何操作。

## 双语开源规范 / Bilingual Open-Source Convention

### 中文

- 文件、模块、类型、函数、变量和常量统一使用英文 identifier。
- README、重要架构文档和状态文档同时提供完整中文与英文信息。
- 新增或实际修改的重要 public API 使用简洁的中英双语 docstring。
- 只有业务规则、金融约定、安全限制或非显然设计才增加双语注释。
- 历史内容在未来实际修改时逐步迁移，不为翻译一次性重写整个仓库。

### English

- Files, modules, types, functions, variables, and constants use English identifiers.
- The README and important architecture and status documentation provide complete information in both Chinese and English.
- New or materially changed public APIs use concise bilingual docstrings.
- Bilingual comments are reserved for business rules, financial conventions, safety constraints, and non-obvious design decisions.
- Existing content migrates progressively when it is changed; internationalization does not require a repository-wide rewrite.
