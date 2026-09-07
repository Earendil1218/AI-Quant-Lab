"""Paper execution foundation public API. / Paper 执行基础公共接口，真实订单锁闭。"""

from broker.ibkr.adapter import IBKRPaperAdapter
from broker.ibkr.config import PaperExecutionConfig, PaperSafetyError
from broker.ibkr.connection import paper_observation_session
from broker.ibkr.events import IBKREventNormalizer
from broker.ibkr.mapping import EquityContractSpec
from broker.ibkr.models import IBKROrderIdentity, IdentityRegistry
from broker.ibkr.transport import ReadOnlyIBKRTransport

__all__ = [
    "IBKRPaperAdapter", "PaperExecutionConfig", "PaperSafetyError", "paper_observation_session",
    "IBKREventNormalizer", "EquityContractSpec", "IBKROrderIdentity", "IdentityRegistry",
    "ReadOnlyIBKRTransport",
]
