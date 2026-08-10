"""只读测试：连接本机 TWS 模拟账户并读取账户与 NVDA 行情。"""

from __future__ import annotations

from ib_insync import IB, Stock


HOST = "127.0.0.1"
PORT = 7497
CLIENT_ID = 1


def print_account_summary(ib: IB) -> None:
    """输出账户摘要。"""
    print("\n账户摘要:")
    for item in ib.accountSummary():
        print(f"  {item.account} | {item.tag}: {item.value} {item.currency}")


def print_nvda_price(ib: IB) -> None:
    """请求并输出 NVDA 最新可用价格。"""
    contract = Stock("NVDA", "SMART", "USD")
    ib.qualifyContracts(contract)

    # 1 = 实时行情；若账户没有实时订阅，IBKR 通常会返回 -1 错误。
    # 切换到 3 后可请求延迟行情（在 IBKR 允许时）。
    ib.reqMarketDataType(3)
    ticker = ib.reqMktData(contract, "", False, False)
    ib.sleep(10)

    price = ticker.marketPrice()
    if price is None or price != price:  # NaN
        price = ticker.last or ticker.close

    if price is None or price != price:
        print("\nNVDA 最新价格不可用；请确认 TWS 已登录且市场数据权限可用。")
    else:
        print(f"\nNVDA 最新价格: {price:.2f} USD")

    ib.cancelMktData(contract)


def main() -> None:
    ib = IB()
    try:
        print(f"连接 TWS 模拟账户：{HOST}:{PORT} ...")
        ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=10, readonly=True)
        print("连接成功。")

        print_account_summary(ib)
        print_nvda_price(ib)
    except Exception as exc:
        print(f"连接或读取数据失败: {exc}")
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("\n已断开 TWS 连接。")


if __name__ == "__main__":
    main()
