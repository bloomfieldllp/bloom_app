import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Set, Dict, Any

logger = logging.getLogger("app.event_bus")

class EventBus:
    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        message = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        for q in list(self._subscribers):
            try:
                q.put_nowait(message)
            except Exception as e:
                logger.debug(f"Queue push error: {e}")

event_bus = EventBus()
