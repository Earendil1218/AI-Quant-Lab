"""Paper execution public API; real I/O defaults to locked, BUY is explicitly gated."""

from broker.ibkr.adapter import IBKRPaperAdapter
from broker.ibkr.config import PaperExecutionConfig, PaperSafetyError
from broker.ibkr.connection import paper_observation_session
from broker.ibkr.events import IBKREventNormalizer
from broker.ibkr.mapping import EquityContractSpec
from broker.ibkr.models import IBKROrderIdentity, IdentityRegistry
from broker.ibkr.transport import ReadOnlyIBKRTransport
from broker.ibkr.paper_transport import PaperExecutionTransport, PaperSessionConfirmation
from broker.ibkr.recovery import PersistentIdentityRegistry, PersistentIBKRInbox

__all__ = [
    "IBKRPaperAdapter", "PaperExecutionConfig", "PaperSafetyError", "paper_observation_session",
    "IBKREventNormalizer", "EquityContractSpec", "IBKROrderIdentity", "IdentityRegistry",
    "ReadOnlyIBKRTransport", "PaperExecutionTransport", "PaperSessionConfirmation",
    "PersistentIdentityRegistry", "PersistentIBKRInbox",
]
