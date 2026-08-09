# AI-Quant-Lab 项目上下文

## 项目名称

AI-Quant-Lab

## 项目目标

建立一个个人 AI 辅助量化研究实验室，用于：

1. 美股市场研究
2. 股票和期权策略分析
3. Greeks 计算
4. 期权定价模型研究
5. 策略回测
6. 风险管理
7. IBKR API 连接
8. 未来自动化交易系统研究

## 当前技术栈

- Python
- VS Code
- Git
- Codex
- IBKR TWS API
- ib_insync
- pandas
- numpy
- scipy
- matplotlib

## 当前阶段

**Phase 2：股票数据获取和处理**

### 已完成

- ✅ Python 3.11 开发环境与虚拟环境（`.venv311`）配置
- ✅ VS Code 安装
- ✅ Git 初始化
- ✅ Codex 连接
- ✅ AI-Quant-Lab 项目结构创建
- ✅ TWS 模拟账户配置
- ✅ IBKR API 配置
- ✅ 创建 IBKR 连接测试代码
- ✅ IBKR API 连接测试
- ✅ 账户摘要读取测试
- ✅ NVDA 行情获取测试

### 已解决问题

Python 3.14 与 `ib_insync` 的兼容问题已通过切换至 Python 3.11 开发环境解决。

### 当前重点

通过 IBKR API 获取股票历史数据，并建立可复用的数据模块。

### 下一步

1. 测试获取股票历史数据
2. 建立数据模块
3. 建立期权 Greeks 计算模块
4. 搭建策略回测框架
