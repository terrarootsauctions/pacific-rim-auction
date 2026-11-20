# Pacific Rim Auctions: Deployment

This repository has two parts:

- **Static site (repo root):** `index.html`, `listings.html`, `find-assets.html`, `notes-marketplace.html`, `revenue.html` and the rest of the pages, plus `css/` and `js/`. It is served by the included `Dockerfile` and `fly.toml`, or by any static host.
- **Platform backend (`backend/`):** the Python/FastAPI API. See `backend/README.md` for setup, First Hawaiian Bank connection and deployment.

Revenue is received through First Hawaiian Bank, Lihue Branch. No card processor is used.

Secrets (bank webhook secret, account number, database URL) are set in the host's environment settings and are never committed to this repository.
