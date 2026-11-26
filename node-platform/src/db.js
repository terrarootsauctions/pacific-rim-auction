// POSTGRES LAYER - the only place that talks to the database.
// Production uses the `pg` package. There is NO in-memory fallback: if the database is
// unreachable the platform refuses to act (fails closed) instead of losing records.
let driver = null;

function useDriver(d) { driver = d; }           // used by the test harness only

function getDriver() {
  if (driver) return driver;
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error('DATABASE_URL_NOT_SET');
  const { Pool } = require('pg');
  const needSsl = process.env.PGSSL === '1' || /sslmode=require/.test(url);
  driver = new Pool({
    connectionString: url,
    max: Number(process.env.PG_POOL_MAX || 10),
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 10000,
    ssl: needSsl ? { rejectUnauthorized: false } : undefined,
  });
  driver.on('error', (e) => console.error('PG_POOL_ERROR', e.message));
  return driver;
}

async function query(text, params) { return getDriver().query(text, params); }

// Run fn(client) inside one transaction. Commits on return, rolls back on throw.
async function tx(fn) {
  const client = await getDriver().connect();
  try {
    await client.query('BEGIN');
    const out = await fn(client);
    await client.query('COMMIT');
    return out;
  } catch (e) {
    try { await client.query('ROLLBACK'); } catch (_) {}
    throw e;
  } finally {
    client.release();
  }
}

const SCHEMA = `
CREATE TABLE IF NOT EXISTS lots (
  id         TEXT PRIMARY KEY,
  status     TEXT NOT NULL,
  data       JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS bids (
  id     BIGSERIAL PRIMARY KEY,
  lot_id TEXT NOT NULL REFERENCES lots(id),
  amount NUMERIC(20,2) NOT NULL,
  data   JSONB NOT NULL,
  ts     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS bids_lot_idx ON bids(lot_id, amount DESC);
CREATE TABLE IF NOT EXISTS state (
  key        TEXT PRIMARY KEY,
  value      JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit (
  seq   BIGINT PRIMARY KEY,
  ts    TEXT NOT NULL,
  event TEXT NOT NULL,
  si_id TEXT NOT NULL,
  data  TEXT NOT NULL,
  prev  TEXT NOT NULL,
  hash  TEXT NOT NULL
);
`;

async function migrate() { await query(SCHEMA); }
async function ping() { await query('SELECT 1'); return true; }
async function close() { if (driver && driver.end) { await driver.end(); } driver = null; }

module.exports = { useDriver, query, tx, migrate, ping, close, SCHEMA };
