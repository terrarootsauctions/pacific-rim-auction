// LOTS + BIDS - stored in Postgres. Every function takes the open transaction client.
// Lot and bid rows are locked (SELECT ... FOR UPDATE) so two simultaneous bids cannot both win.
const crypto = require('crypto');
const law = require('./lawEngine');

const hydrate = (row) => row && { ...row.data, id: row.id, status: row.status };
const newId = () => `LOT-${Date.now()}-${crypto.randomBytes(3).toString('hex')}`;

async function createLot(c, data) {
  const id = newId();
  const lot = { ...data, id, status: 'OPEN', createdAt: new Date().toISOString(),
    getLicense: !!data.getLicense, hrs467Compliant: !!data.hrs467Compliant, hrs437Compliant: !!data.hrs437Compliant,
    reservePrice: data.reservePrice == null ? null : data.reservePrice };
  await c.query('INSERT INTO lots (id, status, data) VALUES ($1, $2, $3::jsonb)', [id, 'OPEN', JSON.stringify(lot)]);
  return lot;
}
async function getLot(c, id, { lock = false } = {}) {
  const r = await c.query('SELECT id, status, data FROM lots WHERE id = $1' + (lock ? ' FOR UPDATE' : ''), [id]);
  return r.rows.length ? hydrate(r.rows[0]) : null;
}
async function getAllLots(c) {
  const r = await c.query('SELECT id, status, data FROM lots ORDER BY created_at DESC LIMIT 1000');
  return r.rows.map(hydrate);
}
async function getBids(c, lotId) {
  const r = await c.query('SELECT id, amount::float8 AS amount, data, ts FROM bids WHERE lot_id = $1 ORDER BY amount DESC, id ASC', [lotId]);
  return r.rows.map((b) => ({ ...b.data, bidId: Number(b.id), amount: Number(b.amount), lotId, ts: b.ts }));
}
async function highestBid(c, lotId) { const b = await getBids(c, lotId); return b.length ? b[0] : null; }

function validateBid(bid) {
  if (!bid || typeof bid.bidderId !== 'string' || !bid.bidderId.trim()) return 'BIDDER_ID_REQUIRED';
  if (typeof bid.amount !== 'number' || !Number.isFinite(bid.amount) || bid.amount <= 0) return 'BID_AMOUNT_MUST_BE_POSITIVE_NUMBER';
  return null;
}

async function placeBid(c, lot, bid) {
  if (lot.status !== 'OPEN') throw new Error('LOT_NOT_OPEN');
  const bad = validateBid(bid); if (bad) throw new Error(bad);
  if (lot.startingPrice != null && bid.amount < lot.startingPrice) throw new Error('BID_BELOW_STARTING_PRICE');
  const top = await highestBid(c, lot.id);
  if (top && bid.amount <= top.amount) throw new Error('BID_MUST_EXCEED_CURRENT_HIGH_BID');
  const entry = { ...bid, amount: bid.amount };
  const r = await c.query('INSERT INTO bids (lot_id, amount, data) VALUES ($1, $2, $3::jsonb) RETURNING id, ts', [lot.id, bid.amount, JSON.stringify(entry)]);
  return { ...entry, lotId: lot.id, bidId: Number(r.rows[0].id), ts: r.rows[0].ts };
}

async function closeLot(c, lot) {
  if (lot.status !== 'OPEN') throw new Error('LOT_NOT_OPEN');
  const highest = await highestBid(c, lot.id);
  let result;
  if (!highest) result = { sold: false, reason: 'NO_BIDS' };
  else if (lot.reserveStatus === 'WITH_RESERVE' && lot.reservePrice != null && highest.amount < lot.reservePrice) result = { sold: false, reason: 'BELOW_RESERVE', highest };
  else result = { sold: true, winner: highest, price: highest.amount };
  const updated = { ...lot, status: 'CLOSED', closeResult: result, closedAt: new Date().toISOString() };
  await c.query('UPDATE lots SET status = $2, data = $3::jsonb WHERE id = $1', [lot.id, 'CLOSED', JSON.stringify(updated)]);
  return { lot: updated, result };
}

async function settleLot(c, lot, { rail, escrowReference }) {
  if (lot.status !== 'CLOSED') throw new Error('LOT_NOT_CLOSED');
  if (!lot.closeResult || !lot.closeResult.sold) throw new Error('NOT_SOLD_CANNOT_SETTLE');
  const fees = law.feeCalc(lot.closeResult.price);
  const updated = { ...lot, fees, rail, escrowReference, status: 'SETTLED', settledAt: new Date().toISOString() };
  await c.query('UPDATE lots SET status = $2, data = $3::jsonb WHERE id = $1', [lot.id, 'SETTLED', JSON.stringify(updated)]);
  return updated;
}

module.exports = { createLot, getLot, getAllLots, getBids, highestBid, placeBid, closeLot, settleLot, validateBid };
