"""Versioned, allowlisted JSON values, without pickle or dynamic imports.

固定类型白名单；Decimal 使用字符串，时间保留显式 offset 或既有 naive 语义。
"""

import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from execution import models, observations
from trading import fills, instruments, orders
from risk import models as risk_models


DOMAIN_TYPES = tuple(
    value for module in (models, observations, fills, instruments, orders, risk_models)
    for value in vars(module).values()
    if isinstance(value, type) and value.__module__ == module.__name__
    and (is_dataclass(value) or issubclass(value, Enum))
)


class Codec:
    """Only explicitly registered immutable records may cross storage.

    只允许显式注册的记录；拒绝 float，避免资金精度静默丢失。
    """

    def __init__(self, extra_types=()):
        self.types = {t.__name__: t for t in (*DOMAIN_TYPES, *extra_types)}

    def _encode(self, value):
        if isinstance(value, Enum):
            if type(value) not in self.types.values():
                raise TypeError("unregistered enum")
            return {"enum": type(value).__name__, "value": value.value}
        if value is None or type(value) in (str, int, bool):
            return value
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise ValueError("nonfinite decimal")
            return {"decimal": str(value)}
        if isinstance(value, datetime):
            return {"datetime": value.isoformat(), "fold": value.fold}
        if isinstance(value, tuple):
            return {"tuple": [self._encode(v) for v in value]}
        if is_dataclass(value) and type(value) in self.types.values():
            return {"type": type(value).__name__, "fields": {
                f.name: self._encode(getattr(value, f.name)) for f in fields(value)}}
        raise TypeError(f"unsupported persistence value: {type(value).__name__}")

    def _decode(self, value):
        if not isinstance(value, dict):
            if value is None or type(value) in (str, int, bool):
                return value
            raise ValueError("invalid stored scalar")
        if "enum" in value:
            return self.types[value["enum"]](value["value"])
        if "decimal" in value:
            result = Decimal(value["decimal"])
            if not result.is_finite():
                raise ValueError("invalid decimal")
            return result
        if "datetime" in value:
            return datetime.fromisoformat(value["datetime"]).replace(fold=value["fold"])
        if "tuple" in value:
            return tuple(self._decode(v) for v in value["tuple"])
        cls = self.types[value["type"]]
        return cls(**{k: self._decode(v) for k, v in value["fields"].items()})

    def dumps(self, value):
        return json.dumps({"schema": 1, "value": self._encode(value)}, sort_keys=True, separators=(",", ":"))

    def loads(self, text):
        document = json.loads(text)
        if document["schema"] != 1:
            raise ValueError("unsupported payload schema")
        return self._decode(document["value"])
