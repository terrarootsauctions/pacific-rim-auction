# PACIFIC RIM AUCTIONS v2 - LIVE - DEPLOY INSTRUCTIONS

Live only. No sandbox, no demo mode, no in-memory fallback. If the database or the SI token is
missing the server refuses to start rather than run unprotected.

## What changed from the version you merged on Nov 20

| # | Problem | Fix (in code) |
|---|---------|---------------|
| 1 | Anyone could call kill / unkill / permission (header defaulted to "SI") | `SI_TOKEN` secret, checked in constant time on every write AND every SI read route. Failed attempts are rate-limited. Server will not start without a 32+ character token. |
| 2 | Gates passed by default (escrow `true`, a default rail, mandates `permissionGranted:true`) | No defaults. Rail and escrowReference must be sent at settlement and the rail must be a known one. A KYC pass counts only with a `kycReference`. Data/settlement country are no longer assumed to be US. Unknown country codes, unknown asset types and a missing `source` now fail. Real-estate disclosures apply to every real-estate lot. |
| 3 | Everything lived in memory | Postgres: lots, bids, permission, kill switch and the audit chain. Restarts lose nothing. Concurrent bids are serialized with row locks. |
| 4 | `package.json` written at runtime, express installed on every boot | `package.json` is at the repo root. Dependency: `pg` only (the web layer is Node built-ins). `npm install` runs at build, `npm start` at start. |
| 5 | 20 files described as 19; country count unchecked | 190 countries loaded and verified unique; `/health` reports `countriesLoaded`. |

Other real bugs found and fixed while testing: closing a lot could never pass (the payment gate saw amount 0); creating a lot demanded a buyer's KYC before any buyer existed; the audit verifier only checked links, not the entries themselves; bids could be lower than the current high bid.

## HONEST LIMITS (read this)

- The platform does not call a KYC or escrow provider. It requires the provider's **reference number** and records it in the audit trail. It checks the reference is present, not that the provider confirms it. Connecting a provider API needs that provider's credentials.
- No money moves in this code. It decides whether a settlement is allowed and records it.
- Roll-out is not automatic. Nothing is live until the files are in GitHub and Render redeploys.

## DEPLOY - existing Render service (phone steps)

Menu names in the Render and GitHub apps can differ slightly from what is written here.

**A. GitHub** (repo `terrarootsauctions/pacific-rim-auction`, branch `main`)
Easiest: use the single-file package (folder `single-file/`). Replace or add these 3 files at the repo root and commit:
1. `package.json`
2. `render.yaml`
3. `bootstrap.js`
(Full source tree is also provided in `pacific-rim-auctions-v2.zip` if you prefer real files.)

**B. Render - database**
1. New > PostgreSQL. Name `pacific-rim-db`, same region as the web service, pick a paid plan (free databases expire).
2. When it is ready, copy its **Internal Database URL**.

**C. Render - web service `pacific-rim-auctions` > Environment**
1. Add `DATABASE_URL` = the Internal Database URL.
2. Add `SI_TOKEN` = a random string of 40+ characters. Save it in your password manager. This is your key.
3. Delete `PERMISSION_GRANTED` (no longer used). `SI_ID` is optional (default `SI`).

**D. Render - web service > Settings**
- Build Command: `npm install`
- Start Command: `npm start`
- Health Check Path: `/health`
- If you used the single-file package, `npm start` runs `node bootstrap.js` (from its package.json). If you used the full tree it runs `node src/server.js`.

**E. Deploy** (Manual Deploy > Deploy latest commit). In Logs you must see:
`Pacific Rim Auctions LIVE on port ... - database connected`
If you see `REFUSING TO START`, the message names exactly what is missing.

**F. Turn it on**
1. Open `https://<your-service>/admin`, paste `SI_TOKEN`.
2. Tap **Grant EXECUTE (30 days)**. Until you do this every action is refused (fail closed).
3. Tap **Health**: `database: connected`, `permissionActive: true`, `countriesLoaded: 190`.
4. Tap **Verify audit chain**: `ok: true`.

New service from scratch instead: Render > New > Blueprint > pick the repo. `render.yaml` creates the database, wires `DATABASE_URL`, and generates `SI_TOKEN` (read it under Environment).

## DAILY USE

- `/admin` - health, audit verify, grant permission, kill switch, dry-run and send requests.
- Kill switch: **KILL** stops every action instantly (stored in the database; survives restarts). **Unkill** restores.
- Rotate the token: change `SI_TOKEN` in Render, redeploy.
- Backups: check your Render database plan's backup and recovery settings; the audit chain and all lots live there.

## API (all SI routes need header `Authorization: Bearer <SI_TOKEN>`)

Public: `GET /health`, `/api/charter`, `/api/countries`, `/api/unclaimed-types`, `/api/assets`
SI: `GET /api/lots`, `/api/lots/:id`, `/api/audit?after=&limit=`, `/api/audit/verify`, `/api/permission`;
`POST /api/permission`, `/api/kill`, `/api/unkill`, `/api/check` (dry run, writes nothing), `/api/lots`, `/api/lots/:id/bid`, `/close`, `/settle`

See `README-WIRED.md` for payloads.
