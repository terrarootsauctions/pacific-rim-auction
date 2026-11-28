"""
Free public data intake. Many counties, cities and states publish property, tax-delinquency,
code-violation and unclaimed-funds records on Socrata open-data portals (SODA API) - no purchase,
no key required (an optional app token raises the rate limit). This pulls rows from such a portal
so they can go through the lead engine.

Safety: the portal host must be a plain public hostname (no IPs, no localhost, no ports), https
only, so this cannot be pointed at internal addresses.
"""
import re
from typing import List, Optional

import requests

MAX_ROWS = 5000
_HOST = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
_DATASET = re.compile(r"^[a-z0-9]{4}-[a-z0-9]{4}$")


class SourceError(ValueError):
    pass


def validate_portal(domain: str, dataset_id: str) -> None:
    d = (domain or "").strip().lower()
    if not _HOST.match(d) or re.match(r"^[\d.]+$", d) or d in ("localhost",) or d.endswith((".local", ".internal")):
        raise SourceError("domain must be a public hostname such as data.example.gov")
    if not _DATASET.match((dataset_id or "").strip().lower()):
        raise SourceError("dataset_id must look like abcd-1234")


def fetch_socrata(domain: str, dataset_id: str, *, limit: int = 1000, offset: int = 0,
                  where: Optional[str] = None, app_token: Optional[str] = None, get=requests.get) -> List[dict]:
    validate_portal(domain, dataset_id)
    limit = max(1, min(int(limit), MAX_ROWS))
    params = {"$limit": limit, "$offset": max(0, int(offset)), "$order": ":id"}
    if where:
        params["$where"] = where
    headers = {"X-App-Token": app_token} if app_token else {}
    url = f"https://{domain.strip().lower()}/resource/{dataset_id.strip().lower()}.json"
    try:
        r = get(url, params=params, headers=headers, timeout=60, allow_redirects=False)
    except requests.RequestException as exc:
        raise SourceError(f"Could not reach {domain}: {exc}")
    if r.status_code != 200:
        raise SourceError(f"{domain} answered HTTP {r.status_code}.")
    try:
        rows = r.json()
    except ValueError:
        raise SourceError(f"{domain} did not return JSON.")
    if not isinstance(rows, list):
        raise SourceError(f"{domain} returned an unexpected response.")
    return rows


_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def validate_ckan(domain: str, resource_id: str) -> None:
    validate_portal(domain, "abcd-1234")
    if not _UUID.match((resource_id or "").strip().lower()):
        raise SourceError("resource_id must be the dataset resource's UUID")


def fetch_ckan(domain: str, resource_id: str, *, limit: int = 1000, offset: int = 0, get=requests.get) -> List[dict]:
    """CKAN open-data portals (used by Australia, Canada, the UK, EU states and many others):
    /api/3/action/datastore_search, read in the portal's own row order."""
    validate_ckan(domain, resource_id)
    limit = max(1, min(int(limit), MAX_ROWS))
    url = f"https://{domain.strip().lower()}/api/3/action/datastore_search"
    try:
        r = get(url, params={"resource_id": resource_id.strip().lower(), "limit": limit, "offset": max(0, int(offset))},
                timeout=60, allow_redirects=False)
    except requests.RequestException as exc:
        raise SourceError(f"Could not reach {domain}: {exc}")
    if r.status_code != 200:
        raise SourceError(f"{domain} answered HTTP {r.status_code}.")
    try:
        body = r.json()
        rows = body["result"]["records"]
    except (ValueError, KeyError, TypeError):
        raise SourceError(f"{domain} did not return CKAN records (is this a datastore-enabled resource?).")
    return [{k: v for k, v in row.items() if k != "_id"} for row in rows if isinstance(row, dict)]
