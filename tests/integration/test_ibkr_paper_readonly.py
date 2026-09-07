"""Opt-in connectivity smoke; never an order test. / 显式连接验证，绝不提交或撤销订单。"""

import os

import pytest

from broker.ibkr import EquityContractSpec, PaperExecutionConfig, paper_observation_session
from broker.ibkr.mapping import map_contract, validate_qualified
from trading import AssetClass, InstrumentId


@pytest.mark.skipif(os.getenv("RUN_IBKR_PAPER_INTEGRATION") != "1", reason="read-only Paper smoke is opt-in")
def test_paper_readonly_connect_account_and_contract():
    config = PaperExecutionConfig.from_env()
    spec = EquityContractSpec(InstrumentId(AssetClass.EQUITY, "NVDA"))
    with paper_observation_session(config, integration_opt_in=True) as transport:
        assert transport.evidence().managed_accounts == (config.account,)
        contracts = transport.qualify(map_contract(spec.instrument, spec))
        assert len(contracts) == 1
        validate_qualified(contracts[0], spec)
