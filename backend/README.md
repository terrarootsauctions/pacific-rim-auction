# Pacific Rim Auctions: Platform Backend

A headless API serving three entities: Pacific Rim Auctions (umbrella), Pacific Rim Auctions LLC, and TerraRoots Global Realty Solutions LLC. Revenue is received through First Hawaiian Bank, Lihue Branch.

**Status: code-complete, not yet boot-verified.** Every file compiles and the internal wiring is consistent, but the app has not been run end to end on a machine with internet access. The first boot (below) is the proof. If something fails, the exact error text points to one file and line.

---

## What this platform does

- Sources and tracks unclaimed, dormant and abandoned assets across 10 categories (real property, financial, business, insurance, transportation, precious/collectible, natural resource, intangible/IP, estate/trust/probate, public/utility).
- Routes real property through TerraRoots Global Realty Solutions LLC, with mandatory inspection (condition, air quality, mineral rights) before it can be listed.
- Lists everything else directly on the Pacific Rim Auctions LLC marketplace.
- Collects a 3-5% platform fee, **received into First Hawaiian Bank**. The platform tells the payer where to send the fee and a unique payment reference; revenue is recorded only when the bank confirms the credit.
- Tracks legal compliance per jurisdiction through a node structure (country plus sub-national region). Every node starts as `PENDING_REVIEW` and only becomes `ACTIVE` after real legal review. Operating target: 190 countries.
- Keeps a permanent, append-only audit log of every consequential action.
- Reapplies earlier human compliance decisions only on an exact match (same country, region, reason and source). Anything else goes to a human.
- Supports outreach (sellers, agents, buyer follow-up) through Reply.io.
- **Follows the sun:** `GET /api/v1/si/follow-the-sun` shows which legally cleared countries are in daytime right now and when the others wake, using the IANA time zone database. Only countries whose jurisdiction node is `ACTIVE` are counted.
- **Heals itself:** outbound calls (Reply.io) retry temporary failures with growing waits, and a circuit breaker pauses a failing service and tests recovery on its own. `GET /api/v1/si/resilience` shows every breaker's state.
- Reports system status and real revenue through the SI briefing endpoint.

## What it deliberately does NOT do

- **It never pays anyone.** No payout, transfer or withdrawal code exists. Receive-only.
- It never reports revenue that the bank has not confirmed.
- Self-healing and self-improvement are advisory: SI reports what is broken and recommends changes. It does not rewrite or deploy code on its own, so the Do No Harm and Follow the Laws of the Land checks cannot be bypassed by accident.

---

## 1. First boot (do this before deploying anywhere)

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# fill in at least SECRET_KEY:
#   python -c "import secrets; print(secrets.token_hex(32))"

uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs**. If you see the Swagger page listing auth, users, assets, listings, bids, payments, admin, outreach, si, jurisdiction-nodes and audit-log, the platform is running.

## 2. Seed the jurisdiction nodes (one time)

```bash
python -m app.scripts.seed_jurisdiction_nodes
```

Nodes come from the real ISO 3166 data and all start as `PENDING_REVIEW`. Attorney findings go in through `PATCH /api/v1/jurisdiction-nodes/{id}/review`. Nothing clears a listing in a country until its node is `ACTIVE`.

## 3. Connect First Hawaiian Bank

Environment variables (set them on the host, never in git):

| Variable | What it is |
|---|---|
| `FHB_ROUTING_NUMBER` | Defaults to the Lihue Branch routing number |
| `FHB_ACCOUNT_NUMBER` | The settlement account |
| `FHB_WEBHOOK_SECRET` | Secret that signs the bank's credit notifications |

How money flows:

1. A buyer calls `POST /api/v1/payments/checkout` and gets the bank details, the amount due and a unique payment reference.
2. The payer sends exactly that amount, quoting the reference.
3. First Hawaiian Bank sends a signed credit notification to `POST /api/v1/payments/bank-webhook` (header `X-FHB-Signature`).
4. If the amount and currency match the fee, the transaction becomes `FEE_COLLECTED` and a balanced ledger entry (BANK_CASH / REVENUE) is written. Each bank event is processed once, so duplicates never double-count.
5. A credit with no matching reference, or the wrong amount, is recorded as cash but **not** as revenue, and appears at `GET /api/v1/admin/bank-events/attention` for a human.

To see whether the rail is really connected, call `GET /api/v1/admin/bank-rail/status`. It reports `not_configured`, `configured_awaiting_first_credit`, or `proven`. It says `proven` only after a real, signed credit from the bank has been received and applied. Settings alone never count as proof.

**Important:** the signature scheme and JSON field names for the bank notification are sensible defaults, not the bank's confirmed specification. Before real money flows, get First Hawaiian Bank's actual incoming-credit notification specification and adjust `verify_signature` and `InboundCreditEvent` in `app/services/payments.py` to match.

Changing the settlement destination: `PUT /api/v1/admin/settlement-destination`. Admin only; requires the admin's password again and the exact phrase `CHANGE SETTLEMENT DESTINATION`. Every change is written to the audit log.

## 4. Run the tests

```bash
pip install pytest
python -m pytest -q tests
```

These cover the retry logic, the circuit breaker, and the Follow the Sun time zone math.

## 5. Deploy

The Dockerfile runs on Render, Google Cloud Run, Fly.io or Railway. Pick one you already have access to. Use a managed Postgres for `DATABASE_URL` in production (SQLite is for local testing only). Set secrets in the host's environment settings.

Render example: create a Web Service from this repo, use the Docker runtime, and add the environment variables above.

## 6. Prove it is live

1. Open `https://YOUR-URL/healthz`. It should return `{"status":"ok"}`.
2. Open `https://YOUR-URL/docs`.
3. Do **one small real test** before relying on it: create a listing, run checkout for a small amount, send that exact amount to the bank with the reference, and confirm `GET /api/v1/admin/revenue` shows it.

---

## File structure

```
pacific-rim-auctions/
├── app/
│   ├── main.py            entrypoint
│   ├── models/            database tables (incl. ledger, bank events,
│   │                      settlement destination, audit log)
│   ├── schemas/           request/response shapes
│   ├── api/               HTTP endpoints by area
│   ├── core/              config, database, auth
│   ├── services/          compliance gate, fees, bank payments, outreach,
│   │                      SI briefing, follow the sun, self-healing, audit logging,
│   │                      precedent matching
│   └── scripts/           jurisdiction seed
├── tests/                 resilience and Follow the Sun tests
├── requirements.txt
├── Dockerfile
├── .env.example
└── .gitignore
```
