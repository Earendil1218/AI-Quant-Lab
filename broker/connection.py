"""建立并验证只读 IBKR TWS 连接。"""

from __future__ import annotations

from ib_insync import IB


def connect_ibkr(
    host: str,
    port: int,
    client_id: int,
    timeout: int = 10,
    readonly: bool = True,
) -> IB:
    """连接 IBKR TWS，并返回已连接的 ``IB`` 对象。"""
    ib = IB()
    ib.connect(
        host,
        port,
        clientId=client_id,
        timeout=timeout,
        readonly=readonly,
    )

    if not ib.isConnected():
        raise ConnectionError(f"无法连接 IBKR TWS：{host}:{port}")

    return ib
