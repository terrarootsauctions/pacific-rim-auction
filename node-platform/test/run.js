// End-to-end tests against a real PostgreSQL. Run: PGTEST_PORT=54329 PGTEST_HOST=/tmp/pgtest node test/run.js
const assert = require('assert');
const http = require('http');
const { Pool } = require('./psqlDriver');
const db = require('../src/db');

const conn = { host: process.env.PGTEST_HOST || '/tmp/pgtest', port: process.env.PGTEST_PORT || 54329, user: 'postgres', db: process.env.PGTEST_DB || 'prtest' };
process.env.SI_TOKEN = 'T'.repeat(40); process.env.SI_ID = 'SI';
db.useDriver(new Pool(conn));
const { buildApp } = require('../src/server');
const audit = require('../src/audit');
const auth = require('../src/auth');

let passed = 0, failed = 0;
async function t(name, fn) { try { await fn(); passed++; console.log('  ok   ' + name); } catch (e) { failed++; console.log('  FAIL ' + name + '\n       ' + (e.stack || e).toString().split('\n').slice(0, 4).join('\n       ')); } }

function call(server, method, path, { body, token = process.env.SI_TOKEN, headers = {} } = {}) {
  return new Promise((resolve, reject) => {
    const data = body === undefined ? null : (typeof body === 'string' ? body : JSON.stringify(body));
    const h = { ...headers }; if (token) h.Authorization = 'Bearer ' + token; if (data) { h['Content-Type'] = 'application/json'; h['Content-Length'] = Buffer.byteLength(data); }
    const r = http.request({ host: '127.0.0.1', port: server.address().port, method, path, headers: h }, (res) => {
      let s = ''; res.on('data', (d) => (s += d)); res.on('end', () => { let j; try { j = JSON.parse(s); } catch (_) { j = s; } resolve({ status: res.statusCode, body: j, headers: res.headers }); });
    });
    r.on('error', reject); if (data) r.write(data); r.end();
  });
}

const kyc = (id) => ({ id, kycPassed: true, kycReference: 'KYC-' + id + '-0001' });
const goodLot = () => ({
  title: 'Waimea House', description: 'From source docs', category: 'REAL_ESTATE', sellerId: 'SELLER-1',
  reserveStatus: 'WITH_RESERVE', reservePrice: 100000, startingPrice: 90000, jurisdictions: ['US'],
  sellerCode: 'US', itemCode: 'US', dataCode: 'US', settlementCode: 'US',
  getLicense: true, hrs467Compliant: true, realEstateLicense: true, source: 'MARKETPLACE', type: 'SINGLE_FAMILY', isPhysical: true,
  reserveDisclosed: true, conditionDisclosed: true, provenanceChecked: true, feesDisclosed: true, buyerPremium: 0.10, sellerCommission: 0.05,
  sellerIdentityDisclosed: true, totalPriceDisclosed: true, titleDisclosed: true, lienDisclosed: true, taxDisclosed: true, hazardDisclosed: true, agencyDisclosed: true, realEstateLicenseChecked: true,
  seller: kyc('SELLER-1'),
});
const grant = () => ({ mode: 'EXECUTE', actionType: 'ALL', limit: null, jurisdiction: 'ALL', expiresAt: new Date(Date.now() + 86400000).toISOString() });
const failedNames = (r) => r.body.failed || [];

(async () => {
  await db.query('DROP TABLE IF EXISTS bids, lots, state, audit CASCADE');
  await db.migrate();
  const server = buildApp().listen(0, '127.0.0.1'); await new Promise((r) => server.on('listening', r));
  console.log('\nAUTH');
  await t('no token -> 401 on kill switch', async () => { const r = await call(server, 'POST', '/api/kill', { token: null, body: {} }); assert.strictEqual(r.status, 401); });
  await t('wrong token -> 401', async () => { const r = await call(server, 'POST', '/api/unkill', { token: 'x'.repeat(40), body: {} }); assert.strictEqual(r.status, 401); });
  await t('old header-only login (x-si-id: SI) no longer works', async () => { const r = await call(server, 'POST', '/api/kill', { token: null, body: {}, headers: { 'x-si-id': 'SI' } }); assert.strictEqual(r.status, 401); });
  await t('read routes are protected too (/api/lots, /api/audit)', async () => { assert.strictEqual((await call(server, 'GET', '/api/lots', { token: null })).status, 401); assert.strictEqual((await call(server, 'GET', '/api/audit', { token: null })).status, 401); });
  await t('short SI_TOKEN is treated as not configured (503)', async () => { const old = process.env.SI_TOKEN; process.env.SI_TOKEN = 'short'; const r = await call(server, 'POST', '/api/kill', { token: 'short', body: {} }); process.env.SI_TOKEN = old; assert.strictEqual(r.status, 503); });
  await t('repeated bad tokens get rate limited (429)', async () => { auth._resetForTests(); let last; for (let i = 0; i < 22; i++) last = await call(server, 'GET', '/api/lots', { token: 'bad' + i }); assert.strictEqual(last.status, 429); auth._resetForTests(); });
  await t('correct token works', async () => { const r = await call(server, 'GET', '/api/permission'); assert.strictEqual(r.status, 200); });

  console.log('\nFAIL-CLOSED GATES');
  await t('no permission on record -> lot creation refused', async () => { const r = await call(server, 'POST', '/api/lots', { body: goodLot() }); assert.strictEqual(r.status, 403); assert(failedNames(r).includes('3_PERMISSION_SI_GRANTED')); });
  await t('permission with no expiry is rejected', async () => { const r = await call(server, 'POST', '/api/permission', { body: { mode: 'EXECUTE' } }); assert.strictEqual(r.status, 400); });
  await t('SI grants permission', async () => { const r = await call(server, 'POST', '/api/permission', { body: grant() }); assert.strictEqual(r.status, 200); });
  await t('good lot passes every gate and is stored', async () => { const r = await call(server, 'POST', '/api/lots', { body: goodLot() }); assert.strictEqual(r.status, 200, JSON.stringify(r.body).slice(0, 400)); assert(r.body.lot.id); });
  await t('lot without KYC reference is refused (bare kycPassed:true is not enough)', async () => { const l = goodLot(); l.seller = { kycPassed: true }; const r = await call(server, 'POST', '/api/lots', { body: l }); assert.strictEqual(r.status, 403); assert(failedNames(r).includes('11_ALL_LEGALITIES_190')); });
  await t('lot with no source is refused', async () => { const l = goodLot(); delete l.source; const r = await call(server, 'POST', '/api/lots', { body: l }); assert.strictEqual(r.status, 403); assert(failedNames(r).includes('9_SOURCE_MARKETPLACE_VS_UNCLAIMED')); });
  await t('missing data/settlement country is not assumed to be US', async () => { const l = goodLot(); delete l.dataCode; delete l.settlementCode; const r = await call(server, 'POST', '/api/lots', { body: l }); assert.strictEqual(r.status, 403); assert(failedNames(r).includes('5_LAWS_190_COUNTRIES')); });
  await t('made-up country code is refused', async () => { const l = goodLot(); l.itemCode = 'XX'; const r = await call(server, 'POST', '/api/lots', { body: l }); assert.strictEqual(r.status, 403); });
  await t('real-estate lot without disclosures is refused even if isRealEstate flag omitted', async () => { const l = goodLot(); delete l.titleDisclosed; delete l.isRealEstate; const r = await call(server, 'POST', '/api/lots', { body: l }); assert.strictEqual(r.status, 403); });
  await t('unknown asset type is refused', async () => { const l = goodLot(); l.type = 'MOON_ROCK'; const r = await call(server, 'POST', '/api/lots', { body: l }); assert.strictEqual(r.status, 403); assert(failedNames(r).includes('8_FULL_ASSET_UNIVERSE')); });
  await t('dry-run /api/check writes nothing', async () => { const before = (await audit.head()).count; await call(server, 'POST', '/api/check', { body: goodLot() }); assert.strictEqual((await audit.head()).count, before); });

  console.log('\nAUCTION FLOW (persisted in Postgres)');
  let lotId;
  await t('create lot', async () => { const r = await call(server, 'POST', '/api/lots', { body: goodLot() }); lotId = r.body.lot.id; assert.strictEqual(r.status, 200); });
  await t('bid without KYC reference is blocked', async () => { const r = await call(server, 'POST', `/api/lots/${lotId}/bid`, { body: { bidderId: 'B1', amount: 95000, buyer: { kycPassed: true } } }); assert.strictEqual(r.status, 403); });
  await t('seller bidding on own lot is blocked (shill)', async () => { const r = await call(server, 'POST', `/api/lots/${lotId}/bid`, { body: { bidderId: 'SELLER-1', amount: 95000, buyer: kyc('SELLER-1'), bidderCode: 'US' } }); assert.strictEqual(r.status, 403); });
  await t('valid bid accepted', async () => { const r = await call(server, 'POST', `/api/lots/${lotId}/bid`, { body: { bidderId: 'B1', amount: 95000, buyer: kyc('B1'), bidderCode: 'US' } }); assert.strictEqual(r.status, 200, JSON.stringify(r.body).slice(0, 300)); });
  await t('bid below current high bid refused', async () => { const r = await call(server, 'POST', `/api/lots/${lotId}/bid`, { body: { bidderId: 'B2', amount: 94000, buyer: kyc('B2'), bidderCode: 'US' } }); assert.strictEqual(r.status, 400); assert.strictEqual(r.body.reason, 'BID_MUST_EXCEED_CURRENT_HIGH_BID'); });
  await t('negative / non-numeric bid refused', async () => { for (const amount of [-5, '120000', null]) { const r = await call(server, 'POST', `/api/lots/${lotId}/bid`, { body: { bidderId: 'B2', amount, buyer: kyc('B2'), bidderCode: 'US' } }); assert.notStrictEqual(r.status, 200); } });
  await t('two simultaneous equal bids: exactly one wins', async () => {
    const mk = (id) => call(server, 'POST', `/api/lots/${lotId}/bid`, { body: { bidderId: id, amount: 110000, buyer: kyc(id), bidderCode: 'US' } });
    const [a, b] = await Promise.all([mk('B3'), mk('B4')]);
    assert.deepStrictEqual([a.status, b.status].sort(), [200, 400], JSON.stringify([a.body,b.body]).slice(0,1200));
  });
  await t('close lot (this used to be impossible: amount 0 failed the payment gate)', async () => { const r = await call(server, 'POST', `/api/lots/${lotId}/close`, { body: {} }); assert.strictEqual(r.status, 200, JSON.stringify(r.body).slice(0, 400)); assert.strictEqual(r.body.result.sold, true, JSON.stringify(r.body).slice(0,600)); assert.strictEqual(r.body.result.price, 110000); });
  await t('bid on closed lot refused', async () => { const r = await call(server, 'POST', `/api/lots/${lotId}/bid`, { body: { bidderId: 'B5', amount: 120000, buyer: kyc('B5'), bidderCode: 'US' } }); assert.notStrictEqual(r.status, 200); });
  await t('settle without escrowReference / rail is blocked', async () => { const r = await call(server, 'POST', `/api/lots/${lotId}/settle`, { body: {} }); assert.strictEqual(r.status, 403); assert(JSON.stringify(r.body).includes('ESCROW')); });
  await t('settle with unknown rail is blocked', async () => { const r = await call(server, 'POST', `/api/lots/${lotId}/settle`, { body: { rail: 'BITCOIN_ATM', escrowReference: 'ESC-0001' } }); assert.strictEqual(r.status, 403); });
  await t('settle with rail + escrowReference succeeds and computes fees', async () => { const r = await call(server, 'POST', `/api/lots/${lotId}/settle`, { body: { rail: 'FIRST_HAWAIIAN', escrowReference: 'ESC-0001' } }); assert.strictEqual(r.status, 200, JSON.stringify(r.body).slice(0, 300)); assert.strictEqual(r.body.lot.status, 'SETTLED'); assert.strictEqual(r.body.lot.fees.buyerPremium, 11000); });

  console.log('\nPERMISSION + KILL SWITCH');
  await t('kill switch stops new lots; unkill restores', async () => {
    assert.strictEqual((await call(server, 'POST', '/api/kill', { body: {} })).status, 200);
    const r = await call(server, 'POST', '/api/lots', { body: goodLot() }); assert.strictEqual(r.status, 403); assert(failedNames(r).includes('3_PERMISSION_SI_GRANTED'));
    assert.strictEqual((await call(server, 'POST', '/api/unkill', { body: {} })).status, 200);
    assert.strictEqual((await call(server, 'POST', '/api/lots', { body: goodLot() })).status, 200);
  });
  await t('permission limit enforced', async () => { await call(server, 'POST', '/api/permission', { body: { ...grant(), limit: 1000 } }); const r = await call(server, 'POST', '/api/lots', { body: goodLot() }); assert.strictEqual(r.status, 403); await call(server, 'POST', '/api/permission', { body: grant() }); });
  await t('OVERSEE mode needs siApproved on each action', async () => { await call(server, 'POST', '/api/permission', { body: { ...grant(), mode: 'OVERSEE' } }); assert.strictEqual((await call(server, 'POST', '/api/lots', { body: goodLot() })).status, 403); assert.strictEqual((await call(server, 'POST', '/api/lots', { body: { ...goodLot(), siApproved: true } })).status, 200); await call(server, 'POST', '/api/permission', { body: grant() }); });

  console.log('\nPERSISTENCE + AUDIT CHAIN');
  await t('state survives a "restart" (new connection pool, same database)', async () => {
    await db.close(); db.useDriver(new Pool(conn));
    const r = await call(server, 'GET', `/api/lots/${lotId}`); assert.strictEqual(r.status, 200); assert.strictEqual(r.body.lot.status, 'SETTLED'); assert(r.body.bids.length >= 2);
    assert.strictEqual((await call(server, 'GET', '/api/permission')).body.permission.mode, 'EXECUTE');
  });
  await t('audit chain verifies', async () => { const v = await audit.verify(); assert.strictEqual(v.ok, true, JSON.stringify(v)); assert(v.count > 20); });
  await t('editing an audit entry is detected (hash mismatch)', async () => {
    await db.query("UPDATE audit SET data = '{\"tampered\":true}' WHERE seq = 3");
    const v = await audit.verify(); assert.strictEqual(v.ok, false); assert.strictEqual(v.reason, 'HASH_MISMATCH'); assert.strictEqual(v.at, 3);
  });
  await t('/health reports database + audit state', async () => { const r = await call(server, 'GET', '/health', { token: null }); assert.strictEqual(r.status, 200); assert.strictEqual(r.body.database, 'connected'); assert.strictEqual(r.body.wired.countriesLoaded, 190); });

  console.log('\nHTTP');
  await t('invalid JSON -> 400, unknown route -> 404', async () => { assert.strictEqual((await call(server, 'POST', '/api/check', { body: '{oops' })).status, 400); assert.strictEqual((await call(server, 'GET', '/nope', { token: null })).status, 404); });
  await t('public pages served', async () => { const r = await call(server, 'GET', '/', { token: null }); assert.strictEqual(r.status, 200); const a = await call(server, 'GET', '/admin', { token: null }); assert.strictEqual(a.status, 200); });

  server.close(); await db.close();
  console.log(`\n${passed} passed, ${failed} failed`); process.exit(failed ? 1 : 0);
})();
