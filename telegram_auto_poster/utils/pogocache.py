"""Lightweight in-memory replacement for Valkey used for local testing."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from threading import Lock
from typing import Any, Dict, Optional


class _PogoCacheStore:
    """Container holding shared data for PogoCache clients."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.flushdb()

    def flushdb(self) -> None:
        with self._lock:
            self.strings: Dict[str, str] = {}
            self.hashes: Dict[str, Dict[str, str]] = defaultdict(dict)
            self.sorted_sets: Dict[str, Dict[str, float]] = defaultdict(dict)
            self.sets: Dict[str, set[str]] = defaultdict(set)


_STORE = _PogoCacheStore()


def reset_store() -> None:
    """Reset the global store. Intended for tests only."""

    _STORE.flushdb()


def _ensure_str(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _parse_score(score: Any) -> float:
    if isinstance(score, (int, float)):
        return float(score)
    return float(score or 0)


def _normalize_bounds(bound: Any) -> float:
    if bound in ("-", "-inf", None):
        return float("-inf")
    if bound in ("+", "+inf"):
        return float("inf")
    if isinstance(bound, str) and bound.startswith("("):
        return float(bound[1:])
    return float(bound)


class PogoCachePipeline:
    """Simple pipeline executing queued operations sequentially."""

    def __init__(self, client: "PogoCache") -> None:
        self._client = client
        self._operations: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def execute(self) -> list[Any]:
        results = []
        for name, args, kwargs in self._operations:
            method = getattr(self._client, name)
            results.append(method(*args, **kwargs))
        self._operations.clear()
        return results

    def __getattr__(self, item: str) -> Any:  # pragma: no cover - passthrough
        def wrapper(*args: Any, **kwargs: Any) -> "PogoCachePipeline":
            self._operations.append((item, args, kwargs))
            return self

        return wrapper


class AsyncPogoCachePipeline:
    """Async variant of :class:`PogoCachePipeline`."""

    def __init__(self, client: "AsyncPogoCache") -> None:
        self._client = client
        self._operations: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def execute(self) -> list[Any]:
        results = []
        for name, args, kwargs in self._operations:
            method = getattr(self._client, name)
            results.append(await method(*args, **kwargs))
        self._operations.clear()
        return results

    def __getattr__(self, item: str) -> Any:  # pragma: no cover - passthrough
        def wrapper(*args: Any, **kwargs: Any) -> "AsyncPogoCachePipeline":
            self._operations.append((item, args, kwargs))
            return self

        return wrapper


class PogoCache:
    """Synchronous in-memory cache implementing a Redis-like API."""

    def __init__(self, store: _PogoCacheStore | None = None, **_: Any) -> None:
        self._store = store or _STORE

    def flushdb(self) -> None:
        self._store.flushdb()

    def get(self, key: str) -> str | None:
        return self._store.strings.get(key)

    def set(self, key: str, value: Any) -> bool:
        self._store.strings[key] = _ensure_str(value)
        return True

    def setnx(self, key: str, value: Any) -> int:
        if key in self._store.strings:
            return 0
        self._store.strings[key] = _ensure_str(value)
        return 1

    def delete(self, key: str) -> int:
        removed = 0
        removed += int(self._store.strings.pop(key, None) is not None)
        removed += int(self._store.hashes.pop(key, None) is not None)
        removed += int(self._store.sorted_sets.pop(key, None) is not None)
        removed += int(self._store.sets.pop(key, None) is not None)
        return removed

    def exists(self, key: str) -> int:
        return int(
            key in self._store.strings
            or key in self._store.hashes
            or key in self._store.sorted_sets
            or key in self._store.sets
        )

    def hset(
        self,
        key: str,
        field: str | None = None,
        value: Any | None = None,
        *,
        mapping: Optional[dict[str, Any]] = None,
    ) -> int:
        target = self._store.hashes[key]
        added = 0
        if mapping:
            for f, v in mapping.items():
                added += int(f not in target)
                target[f] = _ensure_str(v)
        elif field is not None and value is not None:
            added = int(field not in target)
            target[field] = _ensure_str(value)
        return added

    def hget(self, key: str, field: str) -> str | None:
        return self._store.hashes[key].get(field)

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._store.hashes.get(key, {}))

    def hdel(self, key: str, field: str) -> int:
        bucket = self._store.hashes.get(key)
        if bucket and field in bucket:
            del bucket[field]
            return 1
        return 0

    def zadd(self, key: str, mapping: dict[str, Any]) -> int:
        target = self._store.sorted_sets[key]
        added = 0
        for member, score in mapping.items():
            added += int(member not in target)
            target[member] = _parse_score(score)
        return added

    def zrem(self, key: str, member: str) -> int:
        target = self._store.sorted_sets.get(key, {})
        if member in target:
            del target[member]
            return 1
        return 0

    def zremrangebyscore(self, key: str, min_score: Any, max_score: Any) -> int:
        target = self._store.sorted_sets.get(key, {})
        low = _normalize_bounds(min_score)
        high = _normalize_bounds(max_score)
        to_delete = [m for m, score in target.items() if low <= score <= high]
        for member in to_delete:
            del target[member]
        return len(to_delete)

    def zrangebyscore(
        self,
        key: str,
        min_score: Any,
        max_score: Any,
        *,
        withscores: bool = False,
        start: int | None = None,
        num: int | None = None,
    ) -> list[Any]:
        target = self._store.sorted_sets.get(key, {})
        low = _normalize_bounds(min_score)
        high = _normalize_bounds(max_score)
        items = [
            (member, score)
            for member, score in sorted(
                target.items(), key=lambda item: (item[1], item[0])
            )
            if low <= score <= high
        ]
        if start is not None or num is not None:
            start_idx = start or 0
            end_idx = start_idx + num if num is not None else None
            items = items[start_idx:end_idx]
        if withscores:
            return [(member, float(score)) for member, score in items]
        return [member for member, _ in items]

    def zcount(self, key: str, min_score: Any, max_score: Any) -> int:
        return len(self.zrangebyscore(key, min_score, max_score))

    def zcard(self, key: str) -> int:
        return len(self._store.sorted_sets.get(key, {}))

    def zincrby(self, key: str, amount: float, member: str) -> float:
        target = self._store.sorted_sets[key]
        target[member] = target.get(member, 0.0) + float(amount)
        return target[member]

    def zrangebylex(
        self,
        key: str,
        min_value: str,
        max_value: str,
        *,
        start: int | None = None,
        num: int | None = None,
    ) -> list[str]:
        items = sorted(self._store.sorted_sets.get(key, {}).keys())
        filtered: list[str] = []
        for item in items:
            if min_value.startswith("["):
                if item < min_value[1:]:
                    continue
            elif min_value.startswith("("):
                if item <= min_value[1:]:
                    continue
            elif min_value != "-":
                if item < min_value:
                    continue

            if max_value.startswith("["):
                if item > max_value[1:]:
                    continue
            elif max_value.startswith("("):
                if item >= max_value[1:]:
                    continue
            elif max_value != "+":
                if item > max_value:
                    continue

            filtered.append(item)
        if start is not None or num is not None:
            start_idx = start or 0
            end_idx = start_idx + num if num is not None else None
            filtered = filtered[start_idx:end_idx]
        return filtered

    def zlexcount(self, key: str, min_value: str, max_value: str) -> int:
        return len(self.zrangebylex(key, min_value, max_value))

    def zrevrange(
        self,
        key: str,
        start: int,
        end: int,
        *,
        withscores: bool = False,
    ) -> list[Any]:
        items = sorted(
            self._store.sorted_sets.get(key, {}).items(),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
        length = len(items)
        if start < 0:
            start = length + start
        if end < 0:
            end = length + end
        start = max(start, 0)
        end = min(end, length - 1)
        if start > end or start >= length:
            return []
        slice_ = items[start : end + 1]
        if withscores:
            return [(member, float(score)) for member, score in slice_]
        return [member for member, _ in slice_]

    def sadd(self, key: str, member: str) -> int:
        target = self._store.sets[key]
        if member in target:
            return 0
        target.add(member)
        return 1

    def sismember(self, key: str, member: str) -> bool:
        return member in self._store.sets.get(key, set())

    def scard(self, key: str) -> int:
        return len(self._store.sets.get(key, set()))

    def incrby(self, key: str, amount: int = 1) -> int:
        value = int(self._store.strings.get(key, "0")) + amount
        self._store.strings[key] = str(value)
        return value

    def decrby(self, key: str, amount: int = 1) -> int:
        value = int(self._store.strings.get(key, "0")) - amount
        self._store.strings[key] = str(value)
        return value

    def incrbyfloat(self, key: str, amount: float) -> float:
        value = float(self._store.strings.get(key, "0")) + float(amount)
        self._store.strings[key] = str(value)
        return value

    def pipeline(self, *_, **__) -> PogoCachePipeline:
        return PogoCachePipeline(self)


class AsyncPogoCache(PogoCache):
    """Asynchronous wrapper around :class:`PogoCache`."""

    async def flushdb(self) -> None:
        await asyncio.to_thread(self._store.flushdb)

    async def get(self, key: str) -> str | None:
        return await asyncio.to_thread(super().get, key)

    async def set(self, key: str, value: Any) -> bool:
        return await asyncio.to_thread(super().set, key, value)

    async def setnx(self, key: str, value: Any) -> int:
        return await asyncio.to_thread(super().setnx, key, value)

    async def delete(self, key: str) -> int:
        return await asyncio.to_thread(super().delete, key)

    async def exists(self, key: str) -> int:
        return await asyncio.to_thread(super().exists, key)

    async def hset(self, *args: Any, **kwargs: Any) -> int:
        return await asyncio.to_thread(super().hset, *args, **kwargs)

    async def hget(self, *args: Any, **kwargs: Any) -> str | None:
        return await asyncio.to_thread(super().hget, *args, **kwargs)

    async def hgetall(self, *args: Any, **kwargs: Any) -> dict[str, str]:
        return await asyncio.to_thread(super().hgetall, *args, **kwargs)

    async def hdel(self, *args: Any, **kwargs: Any) -> int:
        return await asyncio.to_thread(super().hdel, *args, **kwargs)

    async def zadd(self, *args: Any, **kwargs: Any) -> int:
        return await asyncio.to_thread(super().zadd, *args, **kwargs)

    async def zrem(self, *args: Any, **kwargs: Any) -> int:
        return await asyncio.to_thread(super().zrem, *args, **kwargs)

    async def zremrangebyscore(self, *args: Any, **kwargs: Any) -> int:
        return await asyncio.to_thread(super().zremrangebyscore, *args, **kwargs)

    async def zrangebyscore(self, *args: Any, **kwargs: Any) -> list[Any]:
        return await asyncio.to_thread(super().zrangebyscore, *args, **kwargs)

    async def zcount(self, *args: Any, **kwargs: Any) -> int:
        return await asyncio.to_thread(super().zcount, *args, **kwargs)

    async def zcard(self, *args: Any, **kwargs: Any) -> int:
        return await asyncio.to_thread(super().zcard, *args, **kwargs)

    async def zincrby(self, *args: Any, **kwargs: Any) -> float:
        return await asyncio.to_thread(super().zincrby, *args, **kwargs)

    async def zrangebylex(self, *args: Any, **kwargs: Any) -> list[str]:
        return await asyncio.to_thread(super().zrangebylex, *args, **kwargs)

    async def zlexcount(self, *args: Any, **kwargs: Any) -> int:
        return await asyncio.to_thread(super().zlexcount, *args, **kwargs)

    async def zrevrange(self, *args: Any, **kwargs: Any) -> list[Any]:
        return await asyncio.to_thread(super().zrevrange, *args, **kwargs)

    async def sadd(self, *args: Any, **kwargs: Any) -> int:
        return await asyncio.to_thread(super().sadd, *args, **kwargs)

    async def sismember(self, *args: Any, **kwargs: Any) -> bool:
        return await asyncio.to_thread(super().sismember, *args, **kwargs)

    async def scard(self, *args: Any, **kwargs: Any) -> int:
        return await asyncio.to_thread(super().scard, *args, **kwargs)

    async def incrby(self, *args: Any, **kwargs: Any) -> int:
        return await asyncio.to_thread(super().incrby, *args, **kwargs)

    async def decrby(self, *args: Any, **kwargs: Any) -> int:
        return await asyncio.to_thread(super().decrby, *args, **kwargs)

    async def incrbyfloat(self, *args: Any, **kwargs: Any) -> float:
        return await asyncio.to_thread(super().incrbyfloat, *args, **kwargs)

    async def pipeline(self, *_, **__) -> AsyncPogoCachePipeline:
        return AsyncPogoCachePipeline(self)


Valkey = PogoCache
AsyncValkey = AsyncPogoCache
