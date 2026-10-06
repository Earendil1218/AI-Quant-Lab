"""Actual process termination after durable commits, without a worker framework.

真实子进程提交后 os._exit；仅临时数据库，不提供多进程协调能力。
"""

import os
from pathlib import Path
import subprocess
import sys

import pytest

from execution import DispatchOperation
from infrastructure import SQLiteAttemptClaims
from tests.ibkr_fakes import commission, execution
from tests.test_execution_persistence import setup, reopen


CHILD = r'''
import os, sys, socket
from pathlib import Path
from ib_insync import IB
from ib_insync.client import Client
def forbidden(*args, **kwargs):
    raise AssertionError("network/order forbidden in recovery subprocess")
for method in ("connect", "connect_ex", "sendto"):
    setattr(socket.socket, method, forbidden)
socket.create_connection = forbidden
for cls in (IB, Client):
    for method in ("connect", "connectAsync", "placeOrder", "cancelOrder"):
        setattr(cls, method, forbidden)
from infrastructure import SQLiteExecutionRepository, SQLiteAttemptClaims
from execution import ClientOrderId, DispatchOperation
from broker.ibkr.recovery import PersistentIBKRInbox
from tests.ibkr_fakes import at
repo = SQLiteExecutionRepository(Path(sys.argv[1]))
order = repo.get(ClientOrderId("local-logical-order"))
mode = sys.argv[2]
if mode == "claim":
    SQLiteAttemptClaims(repo).claim(order, DispatchOperation.SUBMIT)
    os._exit(23)
if mode == "fill":
    observation = PersistentIBKRInbox(repo, "offline-session", 3).replay()[-1]
    repo.apply_observation(observation, applied_at=at(9), expected_version=order.version)
    os._exit(24)
if mode == "account":
    state = repo.account_pending()
    print(str(state.cash), sum(state.quantities.values()), repo.pending_accounting_count())
'''


def child(repo, mode):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", RUN_IBKR_PAPER_INTEGRATION="0")
    return subprocess.run([sys.executable, "-B", "-c", CHILD, str(repo.path), mode],
                          cwd=Path(__file__).resolve().parents[1], env=env,
                          capture_output=True, text=True, timeout=30)


def test_process_exit_after_claim_retains_send_prohibition(tmp_path):
    repo, pending, fake, _, _ = setup(tmp_path)
    result = child(repo, "claim")
    assert result.returncode == 23, result.stderr
    fresh = reopen(repo)
    with pytest.raises(ValueError, match="claimed"):
        SQLiteAttemptClaims(fresh).claim(pending, DispatchOperation.SUBMIT)
    assert fresh.list_recovery_candidates()[0].claimed_operations == ("submit",)
    assert not fake.placed


def test_process_exit_after_fill_new_process_accounts_once(tmp_path):
    repo, pending, _, adapter, inbox = setup(tmp_path)
    adapter.submit(pending)
    inbox.append(commission()); inbox.append(execution())
    result = child(repo, "fill")
    assert result.returncode == 24, result.stderr
    fresh = reopen(repo)
    assert fresh.pending_accounting_count() == 1
    assert fresh.get(pending.client_order_id).cumulative_filled_quantity == 100
    first = child(repo, "account")
    second = child(repo, "account")
    assert first.returncode == second.returncode == 0, first.stderr + second.stderr
    assert first.stdout.strip() == second.stdout.strip() == "9999 100 0"
