// SI AUTHENTICATION - one secret token (SI_TOKEN), checked in constant time.
// The old code trusted a header and defaulted to "SI" with no secret at all.
const crypto = require('crypto');

const MIN_LEN = 32;
const fails = new Map(); // ip -> {n, reset}
const MAX_FAILS = 20, WINDOW_MS = 15 * 60 * 1000;

function configured() {
  const t = process.env.SI_TOKEN;
  return typeof t === 'string' && t.length >= MIN_LEN;
}

function safeEqual(a, b) {
  const ha = crypto.createHash('sha256').update(String(a)).digest();
  const hb = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(ha, hb);
}

function clientIp(req) {
  const xf = req.headers['x-forwarded-for'];
  return (xf ? String(xf).split(',')[0].trim() : req.socket.remoteAddress) || 'unknown';
}

function tokenFrom(req) {
  const h = req.headers['authorization'] || '';
  const m = /^Bearer\s+(.+)$/i.exec(h);
  return m ? m[1].trim() : (req.headers['x-si-token'] || '');
}

// Returns {ok, status, reason}
function check(req) {
  if (!configured()) return { ok: false, status: 503, reason: 'SI_TOKEN_NOT_CONFIGURED' };
  const ip = clientIp(req), now = Date.now();
  const f = fails.get(ip);
  if (f && f.reset > now && f.n >= MAX_FAILS) return { ok: false, status: 429, reason: 'TOO_MANY_FAILED_ATTEMPTS' };
  const tok = tokenFrom(req);
  if (tok && safeEqual(tok, process.env.SI_TOKEN)) { fails.delete(ip); return { ok: true }; }
  const cur = f && f.reset > now ? f : { n: 0, reset: now + WINDOW_MS };
  cur.n += 1; fails.set(ip, cur);
  return { ok: false, status: 401, reason: 'SI_TOKEN_REQUIRED' };
}

function siId() { return process.env.SI_ID || 'SI'; }

function _resetForTests() { fails.clear(); }

module.exports = { check, configured, siId, MIN_LEN, _resetForTests };
