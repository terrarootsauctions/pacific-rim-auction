"""Continuous background work (the 24/7 loop).

Every task is wrapped so one failure never stops the loop; failures are
logged and the next cycle tries again. Safe with several instances: auction
closing uses row locks (skip locked) and never closes twice."""
import asyncio
import logging
from datetime import datetime

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services import auction_engine, memory_lock, publisher
from app.services.realtime import manager

log = logging.getLogger("pacific_rim.background")


def _close_due_sync():
    with SessionLocal() as db:
        return auction_engine.close_due_auctions(db, datetime.utcnow())


def _verify_sync():
    with SessionLocal() as db:
        return memory_lock.verify_all(db, trigger="scheduled")


async def close_loop(stop: asyncio.Event) -> None:
    interval = max(1, get_settings().auction_close_interval_seconds)
    while not stop.is_set():
        try:
            events = await asyncio.to_thread(_close_due_sync)
            for e in events:
                lid = e.get("listing_id")
                if lid:
                    await manager.broadcast(lid, e)
        except Exception:  # noqa: BLE001
            log.exception("auction close cycle failed; will retry")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def verify_loop(stop: asyncio.Event) -> None:
    interval = max(60, get_settings().memory_verify_interval_seconds)
    while not stop.is_set():
        try:
            result = await asyncio.to_thread(_verify_sync)
            if result["status"] != "VERIFIED":
                log.error("MEMORY INTEGRITY FAILURE: %s", result)
        except Exception:  # noqa: BLE001
            log.exception("memory verification cycle failed; will retry")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


def _recheck_sync():
    with SessionLocal() as db:
        return publisher.recheck_all(db, datetime.utcnow())


async def recheck_loop(stop: asyncio.Event) -> None:
    """Daily gate recheck: listings still waiting on a legal-review result,
    signature or recorded basis are tried again each pass, and the ones that
    now qualify go live. Failures are logged and retried next pass."""
    interval = max(300, get_settings().gate_recheck_interval_seconds)
    while not stop.is_set():
        try:
            result = await asyncio.to_thread(_recheck_sync)
            log.info("gate recheck: %s", result)
        except Exception:  # noqa: BLE001
            log.exception("gate recheck cycle failed; will retry")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
