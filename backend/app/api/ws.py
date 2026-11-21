from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.models.listing import Listing
from app.models.user import User
from app.services import auction_engine
from app.services.realtime import manager

router = APIRouter(tags=["realtime"])


def _authorize_and_snapshot(token: str, listing_id: str):
    """Re-authenticate and fetch authoritative state. Returns (state, error)."""
    user_id = decode_access_token(token)
    if user_id is None:
        return None, "unauthorized"
    with SessionLocal() as db:
        if db.get(User, user_id) is None:
            return None, "unauthorized"
        listing = db.get(Listing, listing_id)
        if listing is None:
            return None, "not_found"
        return auction_engine.snapshot(db, listing), None


def _fresh_state(listing_id: str):
    with SessionLocal() as db:
        listing = db.get(Listing, listing_id)
        return auction_engine.snapshot(db, listing) if listing else None


@router.websocket("/ws/listings/{listing_id}")
async def listing_socket(websocket: WebSocket, listing_id: str, token: str = Query(...)):
    """Live auction feed. Connect with ?token=<login token>. On connect (and
    on every reconnect) the server re-authenticates and sends the complete
    authoritative state. Send the text "SYNC" at any time, for example after
    noticing a gap in sequence numbers, to receive a full state refresh."""
    state, error = await run_in_threadpool(_authorize_and_snapshot, token, listing_id)
    if error == "unauthorized":
        await websocket.close(code=4401)
        return
    if error == "not_found":
        await websocket.close(code=4404)
        return

    await manager.connect(listing_id, websocket)
    try:
        await websocket.send_json({"type": "STATE", **state})
        while True:
            message = await websocket.receive_text()
            if message.strip().upper() == "SYNC":
                fresh = await run_in_threadpool(_fresh_state, listing_id)
                if fresh is not None:
                    await websocket.send_json({"type": "STATE", **fresh})
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(listing_id, websocket)
