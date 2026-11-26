// PACIFIC RIM AUCTIONS - ALL IN CODE - ONE MASTER
// One require loads everything: 190 + Unclaimed + Assets + All Legalities + Engine
const legal190 = require('./legal190');
const unclaimed = require('./unclaimedFull190');
const assets = require('./fullAssetUniverse');
const allLeg = require('./allLegalities190');
const legalEngine = require('./legalEngine');
const mandates = require('../mandates');
const permission = require('../permission');
const audit = require('../audit');
const law = require('../lawEngine');
const auction = require('../auction');
const { preExecutionCheck } = require('../preExecutionCheck');
const LIVE_MODE_ONLY = true;
const TOTAL_COUNTRIES = 190;
// Single entry point: runs the full gate. ctx = { client, actionType, amount, lot, bid, buyer, seller, trustee, siId, input, ... }
// `client` is the open database transaction (see src/db.js tx()).
const checkEverythingAsCode = (ctx) => preExecutionCheck(ctx);
module.exports = { LIVE_MODE_ONLY, TOTAL_COUNTRIES, legal190, unclaimed, assets, allLeg, legalEngine, mandates, permission, audit, law, auction, preExecutionCheck, checkEverythingAsCode };
