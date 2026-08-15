# AI-Quant-Lab

AI-Quant-Lab 是一个用于美股数据研究、期权分析、策略回测和风险管理的学习型量化研究项目。

当前已完成 Phase 2：通过 IBKR TWS Paper Trading API 以只读方式获取股票历史数据，完成基础质量验证，并以 CSV 保存和重新加载。项目不会提交、修改或撤销订单。

## 运行环境

- Python 3.11
- IBKR TWS Paper Trading，并启用 API 连接
- `ib-insync`
- `pandas`

安装项目的直接依赖：

```powershell
python -m pip install -r requirements.txt
```

## 项目结构

```text
AI-Quant-Lab/
├── main.py              # 历史数据测试流程入口
├── config/              # 环境变量和默认运行配置
├── broker/              # IBKR 连接及市场数据访问
├── data/
│   ├── storage.py       # CSV 文件命名、保存与读取
│   ├── validation.py    # 市场数据基础质量验证
│   ├── raw/             # 从 IBKR 获取的原始行情 CSV
│   └── processed/       # 处理后数据目录，当前阶段暂不使用
├── pricing/             # 期权定价与 Greeks，后续阶段实现
├── strategies/          # 策略定义，后续阶段实现
├── backtest/            # 策略回测，后续阶段实现
├── risk/                # 风险度量与控制，后续阶段实现
├── notebooks/           # 探索性研究笔记
├── tests/               # 不依赖真实 TWS 的离线测试
└── docs/                # 项目状态、决策和路线图
```

各模块的职责边界：

- `config`：集中读取 IBKR 连接参数和默认历史数据参数。
- `broker`：建立只读 TWS 连接，并将 IBKR 历史数据转换为 pandas DataFrame。
- `data`：验证市场数据，并负责本地 CSV 的规范命名、保存和重新读取。
- `pricing`：未来放置定价模型及 Greeks 计算。
- `strategies`：未来放置研究策略定义，不在当前阶段执行交易。
- `backtest`：未来放置历史回测功能。
- `risk`：未来放置风险指标与控制逻辑。
- `tests`：验证模块接口和市场数据转换，默认不连接真实 TWS。

原始行情采用以下文件命名规则：

```text
SYMBOL_INTERVAL.csv
```

当前已支持日线映射：

```text
NVDA + "1 day" → data/raw/NVDA_1d.csv
```

未知 K 线粒度不会自动拼接文件名，需要先在代码和测试中明确增加映射。

## 配置

项目优先读取以下环境变量，并在 `config/settings.py` 中提供开发默认值：

- `IBKR_HOST`，默认 `127.0.0.1`
- `IBKR_PORT`，默认 `7497`
- `IBKR_CLIENT_ID`，默认 `2`
- `DEFAULT_SYMBOL`，默认 `NVDA`
- `DEFAULT_DURATION`，默认 `1 Y`
- `DEFAULT_BAR_SIZE`，默认 `1 day`

可参考 `.env.example` 设置本地环境变量。Python 不会自动加载 `.env` 文件；使用 VS Code、PowerShell 或操作系统环境变量传入配置即可。不要将 `.env` 提交到 Git。

## 获取并保存历史数据

启动并登录 TWS Paper Trading、确认 API 端口为 `7497` 后运行：

```powershell
python -u main.py
```

程序会执行以下流程：

```text
连接 TWS Paper Trading
→ 获取默认标的历史日线
→ 验证必要字段、日期和 OHLC
→ 保存到 data/raw/
→ 从 CSV 重新读取并再次验证
→ 比较行数和日期范围
→ 输出摘要
→ 断开连接
```

连接使用 `readonly=True`。真实 CSV 文件由 `.gitignore` 排除，不应提交到 Git。

## 运行离线测试

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -p no:cacheprovider -v
```

测试使用内存假对象和 pytest 临时目录，不要求 TWS 在线，不会污染 `data/raw/`，也不会调用订单接口。`-p no:cacheprovider` 用于避免创建 `.pytest_cache`。
