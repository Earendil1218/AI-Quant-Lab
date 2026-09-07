"""Guarded execution adapter without aggregate mutation. / 不修改 aggregate 的执行 adapter。"""

from broker.ibkr.config import PaperExecutionConfig, PaperSafetyError
from broker.ibkr.mapping import EquityContractSpec, map_contract, map_order, prepare_order, validate_qualified
from broker.ibkr.models import IBKROrderIdentity, IdentityRegistry, OrderBinding, integer
from broker.ibkr.transport import IBKRTransport
from execution.adapter import DispatchOperation as Operation, DispatchOutcome as Outcome, DispatchResult
from execution.dispatch import AttemptClaims, StaleIntentError
from execution.models import ExecutionOrder


class IBKRPaperAdapter:
    """Map and dispatch saved intent through a shared claim/identity scope.

    调用方共享 claims/registry，并串行化订单保存与发送；adapter 不保存 aggregate。
    The real transport is locked; offline fakes exercise the exact guarded boundary.
    No returned API value is interpreted as broker acknowledgement.
    """

    def __init__(self, config: PaperExecutionConfig, spec: EquityContractSpec,
                 transport: IBKRTransport, claims: AttemptClaims, registry: IdentityRegistry) -> None:
        self.config = config
        self.spec = spec
        self.transport = transport
        self.claims = claims
        self.registry = registry
        self.generation = transport.generation

    def _preflight(self) -> None:
        self.config.validate(side_effect=True)
        self.transport.evidence().validate(self.config, self.generation)
        self.transport.preflight()

    def submit(self, order: ExecutionOrder) -> DispatchResult:
        """Submit a saved pending snapshot once; mapping/claim conflicts raise.

        保存意图先于副作用；发送前可证明未进入则 NOT_SENT，入口后异常为 DELIVERY_UNKNOWN。
        The consumed claim is never released, including on unknown delivery.
        """
        self.claims.validate(order, Operation.SUBMIT)
        contract = map_contract(order.request.instrument, self.spec)
        if order.broker_order_id is not None:
            raise ValueError("submission cannot reuse a broker-bound order.")
        try:
            self._preflight()
        except PaperSafetyError as exc:
            return DispatchResult(order.client_order_id, Operation.SUBMIT, Outcome.NOT_SENT, str(exc))
        # 中文：无订单副作用的准备先完成；失败不消费 claim，也不分配 broker order ID。
        # English: Finish preparation before claiming; failure consumes neither intent nor order identity.
        qualified = self.transport.qualify(contract)
        if len(qualified) != 1:
            raise ValueError("contract qualification must return exactly one result.")
        contract = qualified[0]
        validate_qualified(contract, self.spec)
        mapped = prepare_order(order.request, self.config.account, self.config.client_id, order.client_order_id)
        try:
            self._preflight()
            self.claims.claim(order, Operation.SUBMIT)
        except (PaperSafetyError, StaleIntentError) as exc:
            return DispatchResult(order.client_order_id, Operation.SUBMIT, Outcome.NOT_SENT, str(exc))
        order_id = integer(self.transport.next_order_id(), "order_id", minimum=1)
        identity = IBKROrderIdentity(self.config.account, self.config.client_id, order_id,
                                     self.generation, order.client_order_id)
        mapped.orderId = order_id
        self.registry.register(OrderBinding(identity, order.request, contract.conId))
        try:
            self.transport.place(contract, mapped)
        except Exception as exc:
            # 中文：入口之后不能证明未送达；不根据异常类型猜测是否安全重试。
            # English: After entry, delivery cannot be disproved; never infer retry safety from exception type.
            return DispatchResult(order.client_order_id, Operation.SUBMIT, Outcome.DELIVERY_UNKNOWN,
                                  f"{type(exc).__name__}: {exc}")
        return DispatchResult(order.client_order_id, Operation.SUBMIT, Outcome.DISPATCH_RETURNED,
                              "transport returned; broker acknowledgement is unresolved")

    def cancel(self, order: ExecutionOrder) -> DispatchResult:
        """Cancel one saved intent using the original API ownership, without retry.

        必须匹配本地请求、账户、session、稳定 broker 身份；返回不代表 CANCELLED。
        """
        self.claims.validate(order, Operation.CANCEL)
        binding = self.registry.get(order.client_order_id)
        identity = binding.identity
        if (binding.request != order.request or identity.account != self.config.account
                or identity.session_generation != self.generation or identity.client_id != self.config.client_id
                or identity.broker_order_id is None or identity.broker_order_id != order.broker_order_id):
            raise ValueError("cancellation identity/request mismatch.")
        mapped = map_order(order.request, identity)
        mapped.permId = identity.perm_id
        try:
            self._preflight()
            self.claims.claim(order, Operation.CANCEL)
        except (PaperSafetyError, StaleIntentError) as exc:
            return DispatchResult(order.client_order_id, Operation.CANCEL, Outcome.NOT_SENT, str(exc))
        try:
            self.transport.cancel(mapped)
        except Exception as exc:
            return DispatchResult(order.client_order_id, Operation.CANCEL, Outcome.DELIVERY_UNKNOWN,
                                  f"{type(exc).__name__}: {exc}")
        return DispatchResult(order.client_order_id, Operation.CANCEL, Outcome.DISPATCH_RETURNED,
                              "cancel request returned; broker outcome is unresolved")
