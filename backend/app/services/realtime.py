"""Real-time auction updates over WebSockets.

Only authoritative, public events are broadcast (type, sequence, current bid,
closing time). No bidder identities. Every event carries the server's
sequence number; a client that sees a gap, or reconnects, asks for a full
state refresh and replaces whatever it had. In-process: with several server
instances, each notifies only its own connected clients."""
from collections import defaultdict
from typing import Dict, Iterable, Set

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._rooms: Dict[str, Set[WebSocket]] = defaultdict(set)

    async def connect(self, listing_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._rooms[listing_id].add(ws)

    def disconnect(self, listing_id: str, ws: WebSocket) -> None:
        self._rooms[listing_id].discard(ws)
        if not self._rooms[listing_id]:
            self._rooms.pop(listing_id, None)

    async def broadcast(self, listing_id: str, message: dict) -> None:
        for ws in list(self._rooms.get(listing_id, ())):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 - a dead socket must not stop the others
                self.disconnect(listing_id, ws)

    async def publish_events(self, listing_id: str, events: Iterable[dict]) -> None:
        for event in events:
            await self.broadcast(listing_id, {**event, "listing_id": listing_id})


manager = ConnectionManager()
