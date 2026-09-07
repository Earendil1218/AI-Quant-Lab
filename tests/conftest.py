"""Default tests must never reach external broker/network I/O. / 默认测试禁止真实 broker/网络 I/O。"""

import os
import socket

import pytest
from ib_insync import IB
from ib_insync.client import Client


@pytest.fixture(autouse=True)
def forbid_external_io(monkeypatch, request):
    """Hard fail even if production code catches a forbidden call.

    即使被测代码捕获异常，teardown 仍失败；仅明确 opt-in 的 integration 可连接。
    Real order entrypoints remain blocked even in the read-only integration test.
    """
    attempted = []

    def forbidden(*args, **kwargs):
        attempted.append(True)
        raise AssertionError("real network/broker side effect forbidden in tests")

    integration = ("integration" in request.node.path.parts
                   and os.getenv("RUN_IBKR_PAPER_INTEGRATION") == "1")
    for cls in (IB, Client):
        for method in ("placeOrder", "cancelOrder"):
            monkeypatch.setattr(cls, method, forbidden)
        if not integration:
            for method in ("connect", "connectAsync"):
                monkeypatch.setattr(cls, method, forbidden)
    if not integration:
        for method in ("connect", "connect_ex", "sendto"):
            monkeypatch.setattr(socket.socket, method, forbidden)
        monkeypatch.setattr(socket, "create_connection", forbidden)
    yield
    assert not attempted, "a forbidden external call was attempted (even if caught)"
