"""Tiny asyncio pub/sub bus. Agents talk only through topics, so any agent can be swapped or scaled."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

log = logging.getLogger("bus")
Handler = Callable[[Any], Awaitable[None] | None]


class Bus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._subs[topic].append(handler)

    async def publish(self, topic: str, payload: Any = None) -> None:
        """Handlers run in subscription order and are awaited (deterministic ordering,
        which matters for bar → stop checks → management → new entries)."""
        for h in list(self._subs.get(topic, [])) + list(self._subs.get("*", [])):
            try:
                res = h(payload) if topic != "*" else h((topic, payload))
                if asyncio.iscoroutine(res):
                    await res
            except Exception:  # an agent failing must never take the bus down
                log.exception("handler %s failed on topic %s", getattr(h, "__qualname__", h), topic)
