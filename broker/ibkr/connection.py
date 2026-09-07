"""Execution connection ownership, separate from historical data. / 执行连接独立于历史行情。"""

from contextlib import contextmanager
from typing import Iterator

from broker.ibkr.config import PaperExecutionConfig
from broker.ibkr.transport import ReadOnlyIBKRTransport


@contextmanager
def paper_observation_session(
    config: PaperExecutionConfig, *, integration_opt_in: bool = False,
) -> Iterator[ReadOnlyIBKRTransport]:
    """Open an opt-in read-only session and always close it, including failures.

    显式连接/查询入口，finally 负责清理；不会创建可发送订单的 transport。
    """
    transport = ReadOnlyIBKRTransport(config)
    try:
        transport.connect_readonly(integration_opt_in=integration_opt_in)
        yield transport
    finally:
        transport.close()
