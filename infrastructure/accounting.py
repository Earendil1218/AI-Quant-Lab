"""Explicit arithmetic for durable accounting reconstruction.

持久化记账使用独立算术策略；禁止受外部 Decimal context 影响或静默舍入。
"""

from contextlib import contextmanager
from decimal import Context, DivisionByZero, Inexact, InvalidOperation, Overflow, ROUND_HALF_EVEN, Rounded, localcontext


ACCOUNTING_POLICY = "decimal-prec50-half-even-exact-v1"


@contextmanager
def accounting_context():
    """50-digit exact arithmetic, with explicit rounding and loss traps.

    50 位精度；不量化至分，超出精度明确失败，不静默截断。
    """
    context = Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                      capitals=1, clamp=0, flags=[],
                      traps=[InvalidOperation, DivisionByZero, Overflow, Inexact, Rounded])
    with localcontext(context):
        yield
