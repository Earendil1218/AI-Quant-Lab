# AI-Quant-Lab

AI-Quant-Lab 是一个用于美股数据研究、期权分析、策略回测和风险管理的学习型量化研究项目。

当前第一阶段聚焦于通过 IBKR TWS Paper Trading API，以只读方式获取股票历史数据。项目不会提交、修改或撤销订单。

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
│   ├── raw/             # 原始数据目录，第一阶段暂不自动写入
│   └── processed/       # 处理后数据目录，第一阶段暂不自动写入
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
- `data`：预留原始数据和处理后数据目录；第一阶段不自动保存行情。
- `pricing`：未来放置定价模型及 Greeks 计算。
- `strategies`：未来放置研究策略定义，不在当前阶段执行交易。
- `backtest`：未来放置历史回测功能。
- `risk`：未来放置风险指标与控制逻辑。
- `tests`：验证模块接口和市场数据转换，默认不连接真实 TWS。

## 配置

项目优先读取以下环境变量，并在 `config/settings.py` 中提供开发默认值：

- `IBKR_HOST`，默认 `127.0.0.1`
- `IBKR_PORT`，默认 `7497`
- `IBKR_CLIENT_ID`，默认 `2`
- `DEFAULT_SYMBOL`，默认 `NVDA`
- `DEFAULT_DURATION`，默认 `1 Y`
- `DEFAULT_BAR_SIZE`，默认 `1 day`

可参考 `.env.example` 设置本地环境变量。Python 不会自动加载 `.env` 文件；使用 VS Code、PowerShell 或操作系统环境变量传入配置即可。不要将 `.env` 提交到 Git。

## 获取历史数据

启动并登录 TWS Paper Trading、确认 API 端口为 `7497` 后运行：

```powershell
python -u main.py
```

程序会以 `readonly=True` 连接 TWS，获取默认标的的历史日线，输出数据摘要，并在结束时断开连接。

## 运行离线测试

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -s tests -v
```

这些基础测试使用内存假对象，不要求 TWS 在线，也不会调用订单接口。
