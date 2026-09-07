"""Offline mapping and identity integrity. / 离线映射与身份完整性。"""

from dataclasses import replace

import pytest

from broker.ibkr.mapping import EquityContractSpec, map_contract, map_order, validate_qualified
from broker.ibkr.models import IBKROrderIdentity, IdentityRegistry, OrderBinding, execution_ids, integer
from execution import ClientOrderId
from tests.ibkr_fakes import NVDA, T0
from trading import AssetClass, InstrumentId, OrderRequest, OrderSide


def identity(**changes):
    return replace(IBKROrderIdentity("DU_TEST", 3, 41, "generation", ClientOrderId("local")), **changes)


@pytest.mark.parametrize("side", [OrderSide.BUY, OrderSide.SELL])
def test_equity_and_market_order_mapping(side):
    spec = EquityContractSpec(NVDA, "NASDAQ")
    contract = map_contract(NVDA, spec)
    assert (contract.symbol, contract.secType, contract.exchange, contract.currency) == ("NVDA", "STK", "SMART", "USD")
    request = OrderRequest(NVDA, side, 37, T0)
    order = map_order(request, identity())
    assert (order.action, order.totalQuantity, order.orderType, order.tif) == (side.name, 37, "MKT", "DAY")
    assert order.account == "DU_TEST" and order.orderRef == "local"
    assert not order.outsideRth and order.transmit
    assert order.orderId == 41 and order.permId == 0


def test_unsupported_instruments_and_qualification_fail_explicitly():
    spec = EquityContractSpec(NVDA)
    with pytest.raises(ValueError):
        map_contract(InstrumentId(AssetClass.EQUITY, "SPY"), spec)
    with pytest.raises(ValueError):
        EquityContractSpec("NVDA")
    contract = map_contract(NVDA, spec)
    with pytest.raises(ValueError):
        validate_qualified(contract, spec)
    contract.conId = 123
    validate_qualified(contract, spec)
    contract.currency = "EUR"
    with pytest.raises(ValueError):
        validate_qualified(contract, spec)


@pytest.mark.parametrize("quantity", [True, 0, -1, 1.5, float("nan"), float("inf"), "10"])
def test_invalid_quantity_never_truncates(quantity):
    with pytest.raises(ValueError):
        integer(quantity, "quantity", minimum=1)


def test_unknown_order_contract_is_not_silently_downgraded():
    class LimitRequest(OrderRequest):
        pass

    with pytest.raises(TypeError):
        map_order(LimitRequest(NVDA, OrderSide.BUY, 10, T0), identity())


def test_identity_bind_once_and_reverse_uniqueness():
    registry = IdentityRegistry()
    binding = OrderBinding(identity(), OrderRequest(NVDA, OrderSide.BUY, 10, T0), 123)
    registry.register(binding)
    registry.register(binding)
    assert binding.identity.broker_order_id is None
    bound = registry.resolve("generation", 3, 41, 9001, "DU_TEST")
    assert bound.identity.broker_order_id.value.endswith(":perm:9001")
    assert registry.resolve("generation", 3, 41, 9001) == bound
    with pytest.raises(ValueError, match="conflicting"):
        registry.resolve("generation", 3, 41, 9002)
    with pytest.raises(ValueError, match="account"):
        registry.resolve("generation", 3, 41, 9001, "OTHER")
    with pytest.raises(ValueError):
        registry.register(replace(binding, identity=identity(client_order_id=ClientOrderId("other"))))
    other = replace(binding, identity=identity(client_order_id=ClientOrderId("other"), order_id=42))
    registry.register(other)
    with pytest.raises(ValueError):
        registry.resolve("generation", 3, 42, 9001)
    with pytest.raises(KeyError):
        registry.resolve("stale-generation", 3, 41, 9001)


def test_fill_identity_deterministic_and_account_scoped():
    assert execution_ids("DU_A", "trade.01") == execution_ids("DU_A", "trade.01")
    assert execution_ids("DU_A", "trade.01") != execution_ids("DU_B", "trade.01")
    assert execution_ids("DU_A", "trade.01") != execution_ids("DU_A", "trade.02")
