# AI Quant Lab

## 项目简介 / Overview

### 中文

AI Quant Lab 是一个持续演进的量化研究项目，长期目标是建设具备真实工程质量的市场数据、研究、回测、期权、组合风险与执行平台。当前 Phase 3 已建立从 IBKR 原始历史行情到标准化 processed 数据集的完整管道。

### English

AI Quant Lab is an evolving quantitative research project whose long-term goal is to become an engineering-focused platform for market data, research, backtesting, options, portfolio risk, and execution. Phase 3 now provides an end-to-end pipeline from raw IBKR history to a normalized processed dataset.

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
├── broker/              # Read-only IBKR connection and market data access
├── data/
│   ├── validation.py    # Data-quality rules
│   ├── processing.py    # Deterministic market-data normalization
│   ├── storage.py       # CSV paths, save, and load
│   ├── raw/             # Source-level historical CSV files
│   └── processed/       # Normalized research-ready CSV files
├── tests/               # Offline tests with no real TWS dependency
├── docs/                # Context, status, decisions, roadmap, and workflow
├── notebooks/           # Exploratory research
├── pricing/             # Future options pricing and Greeks
├── strategies/          # Future strategy research
├── backtest/            # Future backtesting
└── risk/                # Future portfolio and risk controls
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

## 安全边界 / Safety Boundary

### 中文

项目当前仅允许 IBKR Paper Trading 的只读市场数据访问。代码不提交、修改或撤销订单。Paper Trading 自动执行和 Live Trading 都必须经过独立设计、安全审查与明确人工批准。

### English

The project currently permits only read-only market-data access through IBKR Paper Trading. It does not place, modify, or cancel orders. Automated paper execution and live trading require separate design, safety review, and explicit human approval.
