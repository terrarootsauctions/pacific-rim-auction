# Pacific Rim Auctions v2 - ONE PACKET
LIVE ONLY. No sandbox, no demo, no in-memory fallback. Precedence: Mandates > Addendum/Legal > Permission > Transaction Work.
If any live gate fails: PAUSE, PRESERVE, ESCALATE TO SI. Do not force through.
Entry: src/server.js (npm start). Gate: src/preExecutionCheck.js. Storage: Postgres (src/db.js). Auth: SI_TOKEN (src/auth.js).
Tests: `npm test` needs a local Postgres (test/psqlDriver.js). Build single-file package: `npm run pack`.
