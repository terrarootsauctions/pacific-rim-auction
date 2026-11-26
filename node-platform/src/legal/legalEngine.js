
// LEGAL ENGINE - WIRED - CommonJS - re-exports wired modules + core gates
const legal190=require('./legal190'); const unclaimed=require('./unclaimedFull190'); const assets=require('./fullAssetUniverse'); const allLeg=require('./allLegalities190');
const SI={role:'SI',authority:'SOLE_AUTHORITY',humanInLoop:true,allowOutsideHuman:false};
const PRECEDENCE=['MANDATES','ADDENDUM_LEGAL','PERMISSION','TRANSACTION_WORK'];
const STANDARDS={abideByLawsOfEveryCountry:true,doNoHarm:true,selfHeal:true,selfImprove:true};
function checkPermission({permission,action,scope,jurisdiction,amount,now=new Date()}){
  if(!permission) return {pass:false,reason:'NO_PERMISSION: pause, preserve, escalate to SI'};
  if(permission.revoked) return {pass:false,reason:'PERMISSION_REVOKED: freeze all pending transactions'};
  if(permission.expiresAt&&new Date(permission.expiresAt)<now) return {pass:false,reason:'PERMISSION_EXPIRED'};
  if(permission.mode!=='OVERSEE'&&permission.mode!=='EXECUTE') return {pass:false,reason:'INVALID_PERMISSION_MODE'};
  if(permission.mode==='EXECUTE'){
    if(!permission.categories?.includes(action.category)) return {pass:false,reason:`CATEGORY_NOT_PREAUTHORIZED: ${action.category}`};
    if(amount>(permission.limit??0)) return {pass:false,reason:'AMOUNT_EXCEEDS_PERMISSION_LIMIT'};
    if(permission.jurisdictions&&!permission.jurisdictions.includes(jurisdiction)) return {pass:false,reason:`JURISDICTION_NOT_AUTHORIZED: ${jurisdiction}`};
  }
  if(permission.mode==='OVERSEE'&&action.consequential&&!action.siApproved) return {pass:false,reason:'OVERSEE_MODE: SI_APPROVAL_REQUIRED'};
  return {pass:true,reason:'PERMISSION_OK'};
}
function checkDoNoHarm({doubt=false,risk='unknown',state}){ if(doubt||risk==='high'||risk==='unknown') return {pass:false,action:'PAUSE_PRESERVE_ESCALATE',reason:'DO_NO_HARM: doubt detected',preservedState:state??null}; return {pass:true,reason:'DO_NO_HARM_OK'}; }
function detectJurisdictions(tx){return [...new Set([tx.sellerLocation,tx.bidderLocation,tx.itemLocation,tx.dataLocation,tx.settlementLocation].filter(Boolean))];}
function checkLawsOfAllLands({jurisdictions,rules}){ if(!jurisdictions?.length) return {pass:false,reason:'LAW_CHECK: NO_JURISDICTIONS_DETECTED - pause'}; const requires=rules.filter(r=>r.requiresDisclosure); const forbids=rules.filter(r=>r.forbidsDisclosure); if(requires.length&&forbids.length) return {pass:false,action:'PAUSE_PRESERVE_ESCALATE',reason:'LAW_CONFLICT',conflict:{requires,forbids}}; const mostProtective=[...rules].sort((a,b)=>(b.protectiveScore??0)-(a.protectiveScore??0))[0]; return {pass:true,appliedRule:mostProtective,rule:'MOST_PROTECTIVE_RULE_APPLIED',jurisdictions}; }
function resolveReserve({lot,explicitTerms}){const explicitWithoutReserve=/without reserve/i.test(explicitTerms||''); return {lotId:lot.id,withReserve:!explicitWithoutReserve,withoutReserve:explicitWithoutReserve,rule:explicitWithoutReserve?'UCC 2-328: WITHOUT_RESERVE':'UCC 2-328: WITH_RESERVE',mustDiscloseSellerBidding:true};}
function checkShillBidding({lot,bidder,seller}){const reasons=[]; if(bidder.id===seller.id) reasons.push('BIDDER_IS_SELLER'); if(bidder.relatedToSeller) reasons.push('BIDDER_RELATED_TO_SELLER'); if(reasons.length&&!(lot.disclosedReserveBidding===true&&lot.reserveBiddingAllowed===true)) return {pass:false,action:'BLOCK_BID_PAUSE_LOT_ESCALATE_TO_SI',reasons,rule:'SHILL_BIDDING_BLOCKED'}; return {pass:true,reason:'SHILL_CHECK_OK'};}
function routeByCategory({lot}){ if(lot.category==='REAL_ESTATE') return {path:'REAL_ESTATE',requiredLicense:'HRS Chapter 467'}; if(lot.category==='MOTOR_VEHICLE') return {path:'MOTOR_VEHICLE',requiredLicense:'HRS Chapter 437'}; return {path:'CHATTEL',requiredLicense:'HRS 237-9 GET + HRS 445'}; }
function checkHawaiiLicense({seller,categoryPath}){ if(!seller?.getLicense) return {pass:false,reason:'HAWAII: Missing HRS 237-9 GET License - pause lot'}; if(categoryPath.path==='REAL_ESTATE'&&!seller.realEstateLicense) return {pass:false,reason:'HAWAII: Missing HRS 467'}; if(categoryPath.path==='MOTOR_VEHICLE'&&!seller.motorVehicleLicense) return {pass:false,reason:'HAWAII: Missing HRS 437'}; return {pass:true,reason:'HAWAII_LICENSE_OK'}; }
module.exports={SI,PRECEDENCE,STANDARDS,checkPermission,checkDoNoHarm,detectJurisdictions,checkLawsOfAllLands,resolveReserve,checkShillBidding,routeByCategory,checkHawaiiLicense,legal190,unclaimed,assets,allLeg};
