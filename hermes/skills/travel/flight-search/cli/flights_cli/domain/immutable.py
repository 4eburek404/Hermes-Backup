from __future__ import annotations

from copy import deepcopy
from typing import Any


class FrozenDict(dict):
    def _immutable(self, *_: Any, **__: Any) -> None:
        raise TypeError("frozen mapping cannot be mutated")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable

    def __deepcopy__(self, memo: dict[int, Any]) -> FrozenDict:
        del memo
        return self


class FrozenList(list):
    def _immutable(self, *_: Any, **__: Any) -> None:
        raise TypeError("frozen sequence cannot be mutated")

    __setitem__ = _immutable
    __delitem__ = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable

    def __deepcopy__(self, memo: dict[int, Any]) -> FrozenList:
        del memo
        return self


def freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return FrozenDict({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return FrozenList(freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(freeze(item) for item in value)
    return deepcopy(value)


def thaw(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [thaw(item) for item in value]
    return deepcopy(value)
