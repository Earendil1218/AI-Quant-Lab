"""Equity market-order mapping only. / 只支持股票市价单映射。"""

from dataclasses import dataclass

from ib_insync import Contract, MarketOrder, Stock

from broker.ibkr.models import IBKROrderIdentity, integer
from execution.models import ClientOrderId
from trading import AssetClass, InstrumentId, OrderRequest, OrderSide


@dataclass(frozen=True)
class EquityContractSpec:
    """Explicit single US equity universe; no inference from symbol alone.

    domain 没有国家/币种字段，因此显式配置一个美股标的并 qualification，禁止静默 fallback。
    """

    instrument: InstrumentId
    primary_exchange: str = ""

    def __post_init__(self) -> None:
        if type(self.instrument) is not InstrumentId or self.instrument.asset_class is not AssetClass.EQUITY:
            raise ValueError("only an explicit equity InstrumentId is supported.")
        if not isinstance(self.primary_exchange, str):
            raise TypeError("primary_exchange must be a string.")


def map_contract(instrument: InstrumentId, spec: EquityContractSpec) -> Contract:
    """Map the allowlisted equity to STK/SMART/USD, without I/O.

    仅映射显式允许的标的；不匹配立即失败，返回对象仍需唯一 qualification。
    """
    if type(instrument) is not InstrumentId or instrument != spec.instrument:
        raise ValueError("unsupported instrument; explicit single-equity configuration required.")
    return Stock(instrument.symbol, "SMART", "USD", primaryExchange=spec.primary_exchange)


def validate_qualified(contract: Contract, spec: EquityContractSpec) -> None:
    """Reject ambiguous or changed qualification. / 拒绝歧义或被替换的合约。"""
    integer(contract.conId, "conId", minimum=1)
    if (contract.symbol != spec.instrument.symbol or contract.secType != "STK"
            or contract.currency != "USD" or contract.exchange != "SMART"
            or (spec.primary_exchange and contract.primaryExchange != spec.primary_exchange)):
        raise ValueError("qualified contract does not match the configured US equity.")


def map_order(request: OrderRequest, identity: IBKROrderIdentity) -> MarketOrder:
    """Map only the exact current market-request contract, preserving integer shares.

    当前 domain 无 order type/TIF；adapter 固定 MKT/DAY、常规时段，不开放高级订单参数。
    Unknown request subclasses are rejected rather than silently discarding order semantics.
    """
    mapped = prepare_order(request, identity.account, identity.client_id, identity.client_order_id)
    mapped.orderId = identity.order_id
    return mapped


def prepare_order(request: OrderRequest, account: str, client_id: int,
                  client_order_id: ClientOrderId) -> MarketOrder:
    """Validate and map without allocating a broker order ID.

    claim 前完成纯映射；orderId 保持未分配，只有 claim 获胜者才消费 broker identity。
    Only the claim winner allocates and attaches the broker order identity.
    """
    if type(request) is not OrderRequest:
        raise TypeError("only the exact market OrderRequest contract is supported.")
    if request.side not in {OrderSide.BUY, OrderSide.SELL}:
        raise ValueError("unsupported order side.")
    quantity = integer(request.quantity, "quantity", minimum=1)
    return MarketOrder(
        request.side.name, quantity, clientId=client_id,
        account=account, orderRef=client_order_id.value,
        tif="DAY", outsideRth=False, transmit=True,
    )
