"""Context-aware IBKR diagnostics. / 结合上下文的 IBKR 诊断分类。"""

from enum import Enum

from execution.observations import ObservationKind


class ErrorCategory(str, Enum):
    """Stable categories; raw numeric codes stay in this package. / 稳定类别，原始数字留在本包。"""

    INFORMATION = "information"
    CONNECTION = "connection"
    CONTRACT = "contract"
    ORDER = "order"
    REJECTION = "rejection"
    PERMISSION = "permission"
    CANCELLATION = "cancellation"
    UNKNOWN = "unknown"


def classify_error(code: int) -> tuple[ErrorCategory, ObservationKind]:
    """Classify evidence; caller must first resolve request/order context.

    不把所有 error 当拒单，也不把所有 21xx 当信息。未知结果优先保留 unresolved。
    A code alone never authorizes rejection or retry; correlation and state rules still apply.
    """
    if code in {2104, 2106, 2107, 2108, 2158}:
        return ErrorCategory.INFORMATION, ObservationKind.INFORMATION
    if code in {502, 504, 1100, 1101, 1102, 1300, 2110}:
        return ErrorCategory.CONNECTION, ObservationKind.CONNECTION_LOST
    if code == 200:
        return ErrorCategory.CONTRACT, ObservationKind.UNRESOLVED
    if code in {107, 110, 111, 145}:
        return ErrorCategory.ORDER, ObservationKind.UNRESOLVED
    if code == 201:
        return ErrorCategory.REJECTION, ObservationKind.REJECTED
    if code in {203, 354, 10147, 10148}:
        category = ErrorCategory.CANCELLATION if code in {10147, 10148} else ErrorCategory.PERMISSION
        return category, ObservationKind.UNRESOLVED
    if code == 202:
        return ErrorCategory.CANCELLATION, ObservationKind.CANCELLED
    return ErrorCategory.UNKNOWN, ObservationKind.UNRESOLVED
