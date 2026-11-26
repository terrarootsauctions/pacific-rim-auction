// IMMUTABLE AUDIT CHAIN - stored in Postgres, hash-chained, serialized with an advisory lock.
// Each entry's hash covers its exact stored text, so verify() recomputes real hashes
// (the old version only compared prev-links and would not notice an edited entry).
const crypto = require('crypto');
const db = require('./db');

const sha = (s) => crypto.createHash('sha256').update(s).digest('hex');
const material = (seq, ts, event, siId, data, prev) => `${seq}|${ts}|${event}|${siId}|${data}|${prev}`;

// client = the open transaction client, so the audit entry commits or rolls back with the action.
async function log(client, event, data, siId) {
  await client.query('SELECT pg_advisory_xact_lock(7001)');
  const last = await client.query('SELECT seq, hash FROM audit ORDER BY seq DESC LIMIT 1');
  const prev = last.rows.length ? last.rows[0].hash : 'GENESIS';
  const seq = last.rows.length ? Number(last.rows[0].seq) + 1 : 1;
  const ts = new Date().toISOString();
  const dataStr = JSON.stringify(data === undefined ? {} : data);
  const who = siId || 'SI';
  const hash = sha(material(seq, ts, event, who, dataStr, prev));
  await client.query(
    'INSERT INTO audit (seq, ts, event, si_id, data, prev, hash) VALUES ($1,$2,$3,$4,$5,$6,$7)',
    [seq, ts, event, who, dataStr, prev, hash]
  );
  return { seq, ts, event, hash };
}

async function logStandalone(event, data, siId) { return db.tx((c) => log(c, event, data, siId)); }

async function getPage({ after = 0, limit = 200 } = {}) {
  const lim = Math.min(Math.max(Number(limit) || 200, 1), 1000);
  const r = await db.query('SELECT seq, ts, event, si_id, data, prev, hash FROM audit WHERE seq > $1 ORDER BY seq ASC LIMIT ' + lim, [Number(after) || 0]);
  return r.rows.map((e) => ({ ...e, seq: Number(e.seq), data: safeParse(e.data) }));
}
function safeParse(s) { try { return JSON.parse(s); } catch (_) { return s; } }

// Full verification: recompute every hash and check every link.
async function verify() {
  let prev = 'GENESIS', count = 0, after = 0;
  for (;;) {
    const r = await db.query('SELECT seq, ts, event, si_id, data, prev, hash FROM audit WHERE seq > $1 ORDER BY seq ASC LIMIT 500', [after]);
    if (!r.rows.length) break;
    for (const e of r.rows) {
      const seq = Number(e.seq);
      if (seq !== count + 1) return { ok: false, at: seq, reason: 'SEQUENCE_GAP' };
      if (e.prev !== prev) return { ok: false, at: seq, reason: 'BROKEN_LINK' };
      if (sha(material(seq, e.ts, e.event, e.si_id, e.data, e.prev)) !== e.hash) return { ok: false, at: seq, reason: 'HASH_MISMATCH' };
      prev = e.hash; count = seq; after = seq;
    }
  }
  return { ok: true, count, head: prev };
}

async function head() {
  const r = await db.query('SELECT seq, hash FROM audit ORDER BY seq DESC LIMIT 1');
  return r.rows.length ? { count: Number(r.rows[0].seq), head: r.rows[0].hash } : { count: 0, head: 'GENESIS' };
}

module.exports = { log, logStandalone, getPage, verify, head };
