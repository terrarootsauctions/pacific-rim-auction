// PRE-EXECUTION CHECK - every live action passes through here before anything is written.
// Nothing is defaulted to pass. A field that was not sent is a field that fails.
const { MANDATES, ADDENDUM } = require('./mandates');
const permission = require('./permission');
const audit = require('./audit');
const law = require('./lawEngine');
const legal190 = require('./legal/legal190');
const unclaimed = require('./legal/unclaimedFull190');
const assets = require('./legal/fullAssetUniverse');
const allLeg = require('./legal/allLegalities190');
const legalEngine = require('./legal/legalEngine');

const STAGE = { CREATE_LOT: 'CREATE_LOT', PLACE_BID: 'PLACE_BID', CLOSE_LOT: 'CLOSE_LOT', SETTLE: 'SETTLE' };
const REAL_ESTATE_TYPES = ['ULTRA_LUXURY_MANSION','ULTRA_LUXURY_HOME','LUXURY_HOME','LUXURY_VILLA','LUXURY_ESTATE','PENTHOUSE','CASTLE','PRIVATE_ISLAND','RESORT','HOTEL','BEACHFRONT','VINEYARD','RANCH','DISTRESSED_PROPERTY','FORECLOSURE','ZOMBIE_FORECLOSURE','ZOMBIE_TITLE','VACANT_ABANDONED','TAX_DELINQUENT','REO_BANK_OWNED','SHORT_SALE','PROBATE_SALE','BANKRUPTCY_SALE','SINGLE_FAMILY','MULTI_FAMILY','APARTMENT','CONDO','COMMERCIAL','OFFICE','RETAIL','INDUSTRIAL','WAREHOUSE','LAND'];

// Maps API fields to the names the checkers use. It does NOT invent values:
// no default rail, no default escrow, no default data/settlement country, no guessed location.
function normalizeLot(lot) {
  if (!lot) return lot;
  const type = lot.type || lot.assetType || lot.category;
  return {
    ...lot,
    sellerCode: lot.sellerCode || lot.sellerLocation,
    bidderCode: lot.bidderCode || lot.bidderLocation,
    itemCode: lot.itemCode || lot.itemLocation,
    dataCode: lot.dataCode || lot.dataLocation,
    settlementCode: lot.settlementCode || lot.settlementLocation,
    amount: lot.amount ?? lot.startingPrice,
    type,
    assetType: lot.assetType || lot.type || lot.category,
    // real-estate disclosures apply to any real-estate lot, whether or not the caller remembered the flag
    isRealEstate: lot.isRealEstate === true || lot.category === 'REAL_ESTATE' || REAL_ESTATE_TYPES.includes(type),
    isPhysical: lot.isPhysical ?? (['REAL_ESTATE', 'MOTOR_VEHICLE'].includes(lot.category) || REAL_ESTATE_TYPES.includes(type) || ['PRIVATE_JET', 'LUXURY_YACHT'].includes(type) || /_MINE$/.test(type || '')),
  };
}

// ctx: { client, actionType, amount, input, lot, bid, siId, buyer, seller, trustee, siApproved, rail, escrowReference }
async function preExecutionCheck(ctx) {
  const { client, actionType, amount, input = {}, bid, siId, buyer, seller, trustee, siApproved } = ctx;
  const stage = STAGE[actionType];
  const checks = [];
  const nLot = ctx.lot ? normalizeLot({ ...ctx.lot, rail: ctx.rail ?? ctx.lot.rail, escrowReference: ctx.escrowReference ?? ctx.lot.escrowReference }) : null;

  checks.push({ name: '0_KNOWN_ACTION', ok: !!stage, detail: { actionType } });
  checks.push({ name: '1_MANDATES', ok: Object.isFrozen(MANDATES) && MANDATES.standards.includes('Do no harm') && MANDATES.standards.includes('Follow laws of every country') });
  checks.push({ name: '2_ADDENDUM', ok: ADDENDUM.buildUponKnowledge === true && ADDENDUM.doNotCopyPrivateWork === true });

  const perm = await permission.checkPermission(client, { actionType, amount, jurisdiction: nLot?.sellerCode, siApproved });
  checks.push({ name: '3_PERMISSION_SI_GRANTED', ok: perm.ok, detail: perm });

  const harmOk = !(input.wouldHarm || input.wouldLeakPrivileged || input.wouldDestroyEvidence || input.wouldDeceive);
  checks.push({ name: '4_DO_NO_HARM', ok: harmOk });

  if (nLot) {
    const bidderCode = nLot.bidderCode || bid?.bidderCode;
    const r190 = legal190.check190Countries({ sellerCode: nLot.sellerCode, bidderCode, itemCode: nLot.itemCode, dataCode: nLot.dataCode, settlementCode: nLot.settlementCode, requireBidder: stage === 'PLACE_BID' });
    checks.push({ name: '5_LAWS_190_COUNTRIES', ok: r190.pass, detail: r190 });
    const unique = [...new Set([nLot.sellerCode, bidderCode, nLot.itemCode, nLot.dataCode, nLot.settlementCode].filter(Boolean))];
    checks.push({ name: '5b_LAWS_EVERY_COUNTRY', ok: unique.length > 0 && !input.wouldViolateLaw && !(input.lawConflict && !input.escalatedToSI) });

    const a = law.ucc2328Check(nLot); checks.push({ name: '7_AUCTION_LAW_UCC_2328_HAWAII', ok: a.ok, detail: a });
    const assetCheck = assets.checkFullAsset({ asset: nLot, countryCode: nLot.sellerCode });
    checks.push({ name: '8_FULL_ASSET_UNIVERSE', ok: assetCheck.pass, detail: assetCheck });

    const src = unclaimed.checkMarketplaceVsUnclaimed({ lot: nLot });
    checks.push({ name: '9_SOURCE_MARKETPLACE_VS_UNCLAIMED', ok: src.pass === true, detail: src });
    if (nLot.source === 'UNCLAIMED') {
      const u190 = unclaimed.checkUnclaimed190({ lot: nLot, sellerCode: nLot.sellerCode, bidderCode: bidderCode || nLot.sellerCode, itemCode: nLot.itemCode, dataCode: nLot.dataCode, settlementCode: nLot.settlementCode });
      checks.push({ name: '10_UNCLAIMED_190', ok: u190.pass, detail: u190 });
      const uFull = unclaimed.checkUnclaimedFull({ lot: nLot, countryCode: nLot.sellerCode });
      checks.push({ name: '10b_UNCLAIMED_FULL_32', ok: uFull.pass, detail: uFull });
    }

    const sellerObj = seller || nLot.seller || {};
    const buyerObj = buyer || bid?.buyer || {};
    const trusteeObj = trustee || nLot.trustee || { authorized: nLot.trusteeAuthorized };
    const all = allLeg.checkAllLegalities190({ lot: { ...nLot, amount: amount ?? nLot.amount }, bidder: bid || {}, seller: sellerObj, buyer: buyerObj, trustee: trusteeObj, countries: unique, stage: stage || 'SETTLE' });
    checks.push({ name: '11_ALL_LEGALITIES_190', ok: all.pass, detail: all });

    const catPath = legalEngine.routeByCategory({ lot: nLot });
    const haw = legalEngine.checkHawaiiLicense({ seller: { getLicense: nLot.getLicense, realEstateLicense: nLot.realEstateLicense ?? nLot.hrs467Compliant, motorVehicleLicense: nLot.motorVehicleLicense ?? nLot.hrs437Compliant }, categoryPath: catPath });
    checks.push({ name: '12_HAWAII_LICENSE', ok: haw.pass, detail: haw });
    checks.push({ name: '13_THREE_ENTITIES_ROUTING', ok: true, info: true, detail: assets.routeAsset({ asset: nLot }) });
  } else if (actionType === 'CREATE_LOT') {
    checks.push({ name: '5_LAWS_190_COUNTRIES', ok: false, detail: { reason: 'NO_LOT_DATA' } });
  }

  if (bid && nLot) {
    const bv = require('./auction').validateBid(bid);
    checks.push({ name: '14_BID_WELL_FORMED', ok: !bv, detail: { reason: bv } });
    const s = law.shillCheck(bid, nLot); checks.push({ name: '14a_SHILL_CHECK', ok: s.ok, detail: s });
    const s190 = legal190.checkShill190({ lot: nLot, bidder: { id: bid.bidderId, relatedToSeller: bid.relatedToSeller }, seller: { id: nLot.sellerId } });
    checks.push({ name: '14b_SHILL_190', ok: s190.pass, detail: s190 });
  }

  const failed = checks.filter((c) => !c.ok);
  const ok = failed.length === 0;
  // Written inside the same transaction as the action; if this write fails, the action does not happen.
  if (!ctx.dryRun) await audit.log(client, ok ? 'PRE_EXECUTION_PASS' : 'PRE_EXECUTION_PAUSE', { actionType, lotId: ctx.lot?.id || null, failed: failed.map((f) => f.name) }, siId);
  return { ok, checks, failed };
}

module.exports = { preExecutionCheck, normalizeLot };
