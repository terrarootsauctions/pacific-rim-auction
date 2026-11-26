// PACIFIC RIM AUCTIONS - LIVE SERVER
// Every write route: SI token -> database transaction -> pre-execution gate -> action -> audit entry.
// If any step fails, nothing is written (or only the "paused" audit record is).
const { createApp } = require('./http');
const db = require('./db');
const auth = require('./auth');
const audit = require('./audit');
const permission = require('./permission');
const auction = require('./auction');
const law = require('./lawEngine');
const { MANDATES } = require('./mandates');
const { preExecutionCheck } = require('./preExecutionCheck');
const legal190 = require('./legal/legal190');
const unclaimed = require('./legal/unclaimedFull190');
const assets = require('./legal/fullAssetUniverse');

class Reject extends Error { constructor(status, reason, extra) { super(reason); this.status = status; this.reason = reason; this.extra = extra || {}; } }

function requireSI(req, res, next) {
  const a = auth.check(req);
  if (!a.ok) return res.json(a.status, { ok: false, reason: a.reason });
  req.siId = auth.siId();
  next();
}

// Run one action in a single transaction; fn returns {status, body}.
async function act(res, fn) {
  try {
    const out = await db.tx(fn);
    res.json(out.status, out.body);
  } catch (e) {
    if (e instanceof Reject) return res.json(e.status, { ok: false, reason: e.reason, ...e.extra });
    throw e; // becomes a 500: action not performed (transaction rolled back)
  }
}

const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const pause = (message, check) => ({ status: 403, body: { ok: false, paused: true, message, checks: check.checks, failed: check.failed.map((f) => f.name) } });

function buildApp() {
  const app = createApp();

  // ---------- public, read-only ----------
  app.get('/health', async (req, res) => {
    try {
      await db.ping();
      const [head, perm, killed] = await Promise.all([
        audit.head(),
        db.query("SELECT value FROM state WHERE key = 'permission'"),
        db.query("SELECT value FROM state WHERE key = 'kill'"),
      ]);
      const p = perm.rows[0]?.value;
      res.json(200, {
        ok: true, platform: 'Pacific Rim Auctions', live: true, database: 'connected',
        wired: { countries190: legal190.TOTAL_COUNTRIES, countriesLoaded: legal190.COUNTRIES_190.length, unclaimedTypes: unclaimed.UNCLAIMED_TYPES_FULL_32.length, assetTypes: assets.ASSET_UNIVERSE_FULL.length, entities: Object.keys(assets.ENTITIES) },
        permissionActive: !!(p && new Date(p.expiresAt) > new Date()),
        killed: !!(killed.rows[0]?.value?.killed),
        audit: head,
        authConfigured: auth.configured(),
      });
    } catch (e) {
      console.error('HEALTH_FAIL', e.message);
      res.json(503, { ok: false, live: false, database: 'unreachable' });
    }
  });
  app.get('/api/charter', (req, res) => res.json(200, { ok: true, charter: MANDATES, jurisdictions: law.JURISDICTIONS, categories: law.CATEGORIES, fees: law.FEE_SCHEDULE, countries190Count: legal190.TOTAL_COUNTRIES, entities: assets.ENTITIES }));
  app.get('/api/countries', (req, res) => res.json(200, { ok: true, total: legal190.TOTAL_COUNTRIES, countries: legal190.COUNTRIES_190 }));
  app.get('/api/unclaimed-types', (req, res) => res.json(200, { ok: true, types: unclaimed.UNCLAIMED_TYPES_FULL_32, rails: unclaimed.BANKING_RAILS, global: unclaimed.UNCLAIMED_GLOBAL }));
  app.get('/api/assets', (req, res) => res.json(200, { ok: true, entities: assets.ENTITIES, assets: assets.ASSET_UNIVERSE_FULL, rails: assets.BANKING_RAILS_FULL }));

  // ---------- SI only ----------
  app.get('/api/audit', requireSI, async (req, res) => res.json(200, { ok: true, entries: await audit.getPage({ after: req.query.after, limit: req.query.limit }) }));
  app.get('/api/audit/verify', requireSI, async (req, res) => res.json(200, { ok: true, verify: await audit.verify() }));
  app.get('/api/permission', requireSI, async (req, res) => res.json(200, { ok: true, permission: await permission.getPermission(db), killed: await permission.isKilled(db) }));

  app.post('/api/permission', requireSI, (req, res) => act(res, async (c) => {
    let p; try { p = await permission.setPermission(c, req.body, req.siId); } catch (e) { throw new Reject(400, e.message); }
    await audit.log(c, 'PERMISSION_SET', p, req.siId);
    return { status: 200, body: { ok: true, permission: p } };
  }));
  app.post('/api/kill', requireSI, (req, res) => act(res, async (c) => {
    const r = await permission.kill(c, req.siId); await audit.log(c, 'KILL_SWITCH', r, req.siId);
    return { status: 200, body: { ok: true, ...r } };
  }));
  app.post('/api/unkill', requireSI, (req, res) => act(res, async (c) => {
    const r = await permission.unkill(c, req.siId); await audit.log(c, 'UNKILL', r, req.siId);
    return { status: 200, body: { ok: true, ...r } };
  }));

  app.get('/api/lots', requireSI, (req, res) => act(res, async (c) => ({ status: 200, body: { ok: true, lots: await auction.getAllLots(c) } })));
  app.get('/api/lots/:id', requireSI, (req, res) => act(res, async (c) => {
    const lot = await auction.getLot(c, req.params.id); if (!lot) throw new Reject(404, 'LOT_NOT_FOUND');
    return { status: 200, body: { ok: true, lot, bids: await auction.getBids(c, lot.id) } };
  }));

  app.post('/api/lots', requireSI, (req, res) => act(res, async (c) => {
    const { siApproved, ...lotData } = req.body || {};
    if (!lotData.title || typeof lotData.title !== 'string') throw new Reject(400, 'TITLE_REQUIRED');
    if (num(lotData.startingPrice) == null || lotData.startingPrice <= 0) throw new Reject(400, 'STARTING_PRICE_MUST_BE_POSITIVE_NUMBER');
    const check = await preExecutionCheck({
      client: c, actionType: 'CREATE_LOT', amount: lotData.startingPrice, lot: lotData, siId: req.siId, siApproved,
      input: { lawConflict: !!lotData.lawConflict, escalatedToSI: !!lotData.escalatedToSI }, seller: lotData.seller, trustee: lotData.trustee,
    });
    if (!check.ok) return pause('PRE-EXECUTION CHECK FAILED - PAUSE, PRESERVE, ESCALATE TO SI', check);
    const lot = await auction.createLot(c, lotData);
    await audit.log(c, 'LOT_CREATED_LIVE', { id: lot.id, title: lot.title, source: lot.source }, req.siId);
    return { status: 200, body: { ok: true, lot, checks: check.checks } };
  }));

  app.post('/api/lots/:id/bid', requireSI, (req, res) => act(res, async (c) => {
    const lot = await auction.getLot(c, req.params.id, { lock: true }); if (!lot) throw new Reject(404, 'LOT_NOT_FOUND');
    const b = req.body || {};
    const bid = { bidderId: b.bidderId, amount: b.amount, buyer: b.buyer, bidderCode: b.bidderCode, relatedToSeller: !!b.relatedToSeller, collusionSignal: !!b.collusionSignal, maxBid: b.maxBid };
    const check = await preExecutionCheck({ client: c, actionType: 'PLACE_BID', amount: bid.amount, lot, bid, siId: req.siId, siApproved: b.siApproved, input: {}, buyer: bid.buyer, seller: b.seller || lot.seller, trustee: lot.trustee });
    if (!check.ok) return pause('BID BLOCKED - SHILL, LAW, OR PERMISSION', check);
    let entry; try { entry = await auction.placeBid(c, lot, bid); } catch (e) {
      await audit.log(c, 'BID_REFUSED', { lotId: lot.id, reason: e.message }, req.siId);
      return { status: 400, body: { ok: false, reason: e.message } };
    }
    await audit.log(c, 'BID_PLACED_LIVE', { lotId: lot.id, bidId: entry.bidId, amount: entry.amount, bidderId: entry.bidderId }, req.siId);
    return { status: 200, body: { ok: true, bid: entry } };
  }));

  app.post('/api/lots/:id/close', requireSI, (req, res) => act(res, async (c) => {
    const lot = await auction.getLot(c, req.params.id, { lock: true }); if (!lot) throw new Reject(404, 'LOT_NOT_FOUND');
    const top = await auction.highestBid(c, lot.id);
    const check = await preExecutionCheck({ client: c, actionType: 'CLOSE_LOT', amount: top ? top.amount : 0, lot, siId: req.siId, siApproved: req.body?.siApproved, input: {}, seller: req.body?.seller || lot.seller, trustee: lot.trustee });
    if (!check.ok) return pause('CLOSE BLOCKED', check);
    let out; try { out = await auction.closeLot(c, lot); } catch (e) { await audit.log(c, 'CLOSE_REFUSED', { lotId: lot.id, reason: e.message }, req.siId); return { status: 400, body: { ok: false, reason: e.message } }; }
    await audit.log(c, 'LOT_CLOSED_HAMMER_LIVE', { lotId: lot.id, result: out.result }, req.siId);
    return { status: 200, body: { ok: true, ...out } };
  }));

  app.post('/api/lots/:id/settle', requireSI, (req, res) => act(res, async (c) => {
    const lot = await auction.getLot(c, req.params.id, { lock: true }); if (!lot) throw new Reject(404, 'LOT_NOT_FOUND');
    const b = req.body || {};
    const rail = b.rail || lot.rail, escrowReference = b.escrowReference || lot.escrowReference;
    const winner = lot.closeResult?.winner;
    const check = await preExecutionCheck({ client: c, actionType: 'SETTLE', amount: lot.closeResult?.price, lot, siId: req.siId, siApproved: b.siApproved, input: {}, buyer: winner?.buyer, seller: b.seller || lot.seller, trustee: b.trustee || lot.trustee, rail, escrowReference });
    if (!check.ok) return pause('SETTLEMENT BLOCKED - DO NOT MOVE MONEY', check);
    let settled; try { settled = await auction.settleLot(c, lot, { rail, escrowReference }); } catch (e) { await audit.log(c, 'SETTLE_REFUSED', { lotId: lot.id, reason: e.message }, req.siId); return { status: 400, body: { ok: false, reason: e.message } }; }
    await audit.log(c, 'LOT_SETTLED_LIVE', { lotId: lot.id, fees: settled.fees, rail, escrowReference }, req.siId);
    return { status: 200, body: { ok: true, lot: settled } };
  }));

  // Dry run: runs every gate on a payload, writes nothing.
  app.post('/api/check', requireSI, (req, res) => act(res, async (c) => {
    const b = req.body || {}; const lot = b.lot || b;
    const check = await preExecutionCheck({ client: c, dryRun: true, actionType: b.actionType || 'CREATE_LOT', amount: b.amount ?? lot.startingPrice, lot, bid: b.bid, siId: req.siId, siApproved: b.siApproved, input: b.input || {}, buyer: b.buyer || b.bid?.buyer, seller: b.seller || lot.seller, trustee: b.trustee || lot.trustee, rail: b.rail, escrowReference: b.escrowReference });
    return { status: 200, body: { ok: check.ok, checks: check.checks, failed: check.failed.map((f) => f.name) } };
  }));

  return app;
}

async function start() {
  if (!auth.configured()) { console.error(`REFUSING TO START: SI_TOKEN must be set (at least ${auth.MIN_LEN} characters). Set it in Render > Environment.`); process.exit(1); }
  if (!process.env.DATABASE_URL) { console.error('REFUSING TO START: DATABASE_URL is not set. Attach the Render Postgres database.'); process.exit(1); }
  await db.migrate();
  const v = await audit.verify();
  if (!v.ok) { console.error('REFUSING TO START: audit chain failed verification', v); process.exit(1); }
  const port = process.env.PORT || 10000;
  await audit.logStandalone('SERVER_START', { port: Number(port), auditCountAtStart: v.count }, auth.siId());
  const server = buildApp().listen(port, () => console.log(`Pacific Rim Auctions LIVE on port ${port} - database connected - audit entries ${v.count + 1}`));
  const stop = async () => { server.close(); try { await db.close(); } catch (_) {} process.exit(0); };
  process.on('SIGTERM', stop); process.on('SIGINT', stop);
}

module.exports = { buildApp, start };
if (require.main === module) start().catch((e) => { console.error('STARTUP_FAILED', e.message); process.exit(1); });
