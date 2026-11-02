"""In-process pub/sub that feeds the dashboard's server-sent events stream."""

import asyncio
import json
from datetime import datetime
from typing import Any

_subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()


def _default(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"Cannot serialise {type(o).__name__}")


def publish(event: str, data: dict[str, Any]) -> None:
    """Safe to call from any thread or from sync code inside the event loop."""
    payload = json.dumps(data, default=_default)
    for loop, queue in list(_subscribers):
        try:
            loop.call_soon_threadsafe(queue.put_nowait, (event, payload))
        except RuntimeError:  # loop closed
            _subscribers.discard((loop, queue))


async def subscribe():
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    entry = (loop, queue)
    _subscribers.add(entry)
    try:
        while True:
            yield await queue.get()
    finally:
        _subscribers.discard(entry)
