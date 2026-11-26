// MANDATES - constants only. The old file hard-coded permissionGranted:true, which made the
// mandates check pass unconditionally. SI permission is now a live, stored record (permission.js).
const MANDATES = Object.freeze({
  platform: "Pacific Rim Auctions",
  siIsHumanInLoop: true,
  noOutsideHuman: true,
  liveOnly: true,
  precedence: Object.freeze(["Mandates", "Addendum", "Permission", "Transaction"]),
  standards: Object.freeze(["Follow laws of every country", "Do no harm", "Self heal", "Self improve"]),
  charterText: "SI is Human In The Loop. Sole authority. No outside human. Explicit permission only. Do no harm. Follow laws of every country. Self heal. Self improve.",
});
const ADDENDUM = Object.freeze({
  buildUponKnowledge: true,
  doNotBuyPlatforms: true,
  doNotCopyPrivateWork: true,
  integrated: Object.freeze(["Confidential compute", "HYOK", "Zero trust", "Dual check", "Immutable audit + glass archive", "Post-quantum crypto", "SI permission"]),
  legalParts: Object.freeze(["UCC 2-328", "Shill prohibited", "Hawaii HRS 237-9 GET + HRS 445 county", "HRS 467 real estate", "HRS 437 motor vehicle", "Consumer protection", "Pacific Rim jurisdictions", "Escrow settlement"]),
});
module.exports = { MANDATES, ADDENDUM };
