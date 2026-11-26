// SI PERMISSION + KILL SWITCH - stored in Postgres so they survive restarts.
// Fail closed: with no permission on record, every action is refused until SI grants one.
const KEY_PERM = 'permission';
const KEY_KILL = 'kill';

async function get(client, key) {
  const r = await client.query('SELECT value FROM state WHERE key = $1', [key]);
  return r.rows.length ? r.rows[0].value : null;
}
async function put(client, key, value) {
  await client.query(
    'INSERT INTO state (key, value, updated_at) VALUES ($1, $2::jsonb, now()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()',
    [key, JSON.stringify(value)]
  );
}

function validatePermission(p) {
  if (!p || typeof p !== 'object') throw new Error('PERMISSION_BODY_REQUIRED');
  if (!['OVERSEE', 'EXECUTE'].includes(p.mode)) throw new Error('INVALID_MODE');
  if (!p.expiresAt || isNaN(new Date(p.expiresAt).getTime())) throw new Error('EXPIRES_AT_REQUIRED_ISO_DATE');
  if (new Date(p.expiresAt) <= new Date()) throw new Error('EXPIRES_AT_ALREADY_PAST');
  if (p.limit != null && !(Number(p.limit) >= 0)) throw new Error('LIMIT_MUST_BE_NUMBER_OR_NULL');
  return {
    mode: p.mode,
    actionType: p.actionType || 'ALL',
    limit: p.limit == null ? null : Number(p.limit),
    scope: p.scope || 'Pacific Rim Auctions - live transactions within mandates',
    jurisdiction: p.jurisdiction || 'ALL',
    expiresAt: new Date(p.expiresAt).toISOString(),
  };
}

async function setPermission(client, body, siId) {
  const v = validatePermission(body);
  const rec = { ...v, siId, grantedAt: new Date().toISOString() };
  await put(client, KEY_PERM, rec);
  return rec;
}
async function getPermission(client) { return get(client, KEY_PERM); }
async function kill(client, siId) {
  const rec = { killed: true, at: new Date().toISOString(), by: siId };
  await put(client, KEY_KILL, rec); return rec;
}
async function unkill(client, siId) {
  const rec = { killed: false, at: new Date().toISOString(), by: siId };
  await put(client, KEY_KILL, rec); return rec;
}
async function isKilled(client) { const k = await get(client, KEY_KILL); return !!(k && k.killed); }

// siApproved only matters in OVERSEE mode, where SI approves each consequential action.
async function checkPermission(client, { actionType, amount, jurisdiction, siApproved }) {
  if (await isKilled(client)) return { ok: false, reason: 'KILL_SWITCH_ACTIVE' };
  const p = await getPermission(client);
  if (!p) return { ok: false, reason: 'NO_EXPLICIT_PERMISSION_ON_RECORD' };
  if (new Date() > new Date(p.expiresAt)) return { ok: false, reason: 'PERMISSION_EXPIRED' };
  if (p.actionType !== 'ALL' && p.actionType !== actionType) return { ok: false, reason: 'PERMISSION_SCOPE_MISMATCH' };
  if (p.jurisdiction !== 'ALL' && jurisdiction && p.jurisdiction !== jurisdiction) return { ok: false, reason: 'PERMISSION_JURISDICTION_MISMATCH' };
  if (p.limit != null && amount != null && Number(amount) > p.limit) return { ok: false, reason: 'PERMISSION_LIMIT_EXCEEDED' };
  if (p.mode === 'OVERSEE' && siApproved !== true) return { ok: false, reason: 'OVERSEE_MODE_SI_APPROVAL_REQUIRED (send siApproved:true)' };
  return { ok: true, mode: p.mode, granted: true };
}

module.exports = { setPermission, getPermission, kill, unkill, isKilled, checkPermission, validatePermission };
