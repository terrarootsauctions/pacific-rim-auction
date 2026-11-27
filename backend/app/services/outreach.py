"""
Reply.io outreach service.

Real integration against Reply.io's documented v3 API (api.reply.io/v3,
API-key auth in the Authorization header). Used for three outreach
purposes on Pacific Rim Auctions:

  1. Sourcing outreach - contacting potential holders/sellers of
     unclaimed assets to encourage them to list on the platform.
  2. Agent/broker outreach - contacting real estate agents and brokers
     to bring real-estate listings onto the Pacific Rim Auctions LLC
     marketplace.
  3. Buyer follow-up - re-engaging registered users who have not yet
     placed a bid or completed a purchase.

GROUND TRUTH RULE (same standard as payments.py): this file only ever
reports what Reply.io's API actually returns. If the API key isn't
configured or Reply.io rejects a request, calls raise/return an error -
they never silently report success that didn't happen.

This is outreach/marketing infrastructure only. It has no role in
compliance, AML/sanctions screening, or legal review - that is handled
separately via LexisNexis WorldCompliance (see compliance.py).
"""
from enum import Enum
from typing import Optional

import requests

from app.core.config import get_settings
from app.services import resilience

settings = get_settings()


class OutreachCampaignType(str, Enum):
    ASSET_SOURCING = "asset_sourcing"       # potential sellers of unclaimed assets
    AGENT_BROKER = "agent_broker"            # real estate agents/brokers
    BUYER_FOLLOWUP = "buyer_followup"        # registered users, no bid/purchase yet


def _headers() -> dict:
    if not settings.reply_io_api_key:
        raise RuntimeError(
            "REPLY_IO_API_KEY is not configured. Set it in the environment "
            "before calling the Reply.io service - this will not be faked."
        )
    return {
        "Authorization": f"Bearer {settings.reply_io_api_key}",
        "Content-Type": "application/json",
    }


class _TransientHTTPError(Exception):
    """Reply.io answered with a temporary error (429 or 5xx) worth retrying."""


_breaker = resilience.get_breaker("reply_io", failure_threshold=5, recovery_seconds=60)
_TRANSIENT = (requests.ConnectionError, requests.Timeout, _TransientHTTPError)


@resilience.retry_with_backoff(attempts=3, retry_on=_TRANSIENT)
def _send(method: str, url: str, **kwargs) -> dict:
    response = requests.request(method, url, headers=_headers(), timeout=15, **kwargs)
    if response.status_code == 429 or response.status_code >= 500:
        raise _TransientHTTPError(f"Reply.io returned HTTP {response.status_code}")
    response.raise_for_status()  # 4xx (bad key, bad request) is real: raised, never retried
    return response.json()


def _request(method: str, url: str, **kwargs) -> dict:
    """All Reply.io calls go through retry-with-backoff and a circuit
    breaker, so a temporary outage heals itself and a long one stops
    hammering the service. Failures are still raised, never faked."""
    return _breaker.call(_send, method, url, trip_on=_TRANSIENT, **kwargs)


def verify_credentials() -> dict:
    """Calls Reply.io's /whoami endpoint to confirm the API key actually
    works. Use this before relying on any other call in this file."""
    return _request("GET", f"{settings.reply_io_base_url}/whoami")


def add_contact(
    email: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    company: Optional[str] = None,
    country: Optional[str] = None,
    custom_fields: Optional[dict] = None,
) -> dict:
    """Add or update a contact in Reply.io. Used for all three outreach
    types - the campaign_type custom field determines which sequence
    they're eligible for."""
    payload = {
        "email": email,
        "firstName": first_name,
        "lastName": last_name,
        "company": company,
        "country": country,
        "customFields": custom_fields or {},
    }
    return _request("POST", f"{settings.reply_io_base_url}/contacts", json=payload)


def add_contact_to_campaign(contact_id: str, campaign_id: str) -> dict:
    """Enroll an existing contact into a specific Reply.io campaign
    (sequence). campaign_id must correspond to a real campaign already
    created in the Reply.io dashboard - this does not create campaigns,
    only enrolls contacts into ones you've already built there."""
    return _request(
        "POST",
        f"{settings.reply_io_base_url}/campaigns/{campaign_id}/contacts",
        json={"contactId": contact_id},
    )


def get_campaign_stats(campaign_id: str) -> dict:
    """Pull real performance stats (sent, opened, replied) for a campaign -
    the only numbers that should ever be reported as outreach results."""
    return _request("GET", f"{settings.reply_io_base_url}/campaigns/{campaign_id}/stats")


# ---- Webhooks (Reply.io's documented /v3/webhooks endpoints) ----
def list_webhook_events() -> dict:
    """Authoritative list of event names Reply.io can send (GET /v3/webhooks/events)."""
    return _request("GET", f"{settings.reply_io_base_url}/webhooks/events")


def create_webhook(event_type: str, url: str) -> dict:
    return _request("POST", f"{settings.reply_io_base_url}/webhooks",
                    json={"eventType": event_type, "url": url, "scope": "personal"})


def test_webhook(webhook_id: str) -> dict:
    return _request("POST", f"{settings.reply_io_base_url}/webhooks/{webhook_id}/test")


def get_webhook_logs(webhook_id: str) -> dict:
    """Failed-delivery log for one subscription (GET /v3/webhooks/{id}/logs)."""
    return _request("GET", f"{settings.reply_io_base_url}/webhooks/{webhook_id}/logs")
