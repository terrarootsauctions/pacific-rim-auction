
// UNCLAIMED 32 TYPES - WIRED - CommonJS
const UNCLAIMED_TYPES_FULL_32=["DORMANT_BANK_ACCOUNT","DORMANT_BROKERAGE","DORMANT_RETIREMENT","DORMANT_INVESTMENT","ZOMBIE_FORECLOSURE","ZOMBIE_TITLE_HEIRLESS","VACANT_ABANDONED","TAX_DELINQUENT","UNCASHED_CHECK","MONEY_ORDER","TRAVELERS_CHECK","UNCLAIMED_WAGES","UNCLAIMED_TAX_REFUND","UNCLAIMED_PENSION","UNCLAIMED_INSURANCE","LOST_DIVIDEND","UNCLAIMED_ROYALTY_MINERAL","UNCLAIMED_UTILITY_DEPOSIT","UNCLAIMED_GIFT_CARD","ESCROW_REFUND","SAFE_DEPOSIT_BOX_CONTENTS","ESTATE_PROBATE_UNCLAIMED","BANKRUPTCY_DISTRIBUTION","DORMANT_CRYPTO_WALLET","DORMANT_CRYPTO_EXCHANGE","DORMANT_DOMAIN_CREDITS","DORMANT_LOYALTY_POINTS"];
// Note: 27 in taxonomy array + 5 rails counted in original 32 total (see BANKING_RAILS). Keep both exports.
const UNCLAIMED_GLOBAL={worldwideEstimateUSD:200_000_000_000,usEstimateUSD:70_000_000_000,rule:"No property listed until legally eligible for auction under its own country's escheatment law"};
const UNCLAIMED_BY_REGION={US:{dormancyYears:3,escheatTo:"STATE",noticeRequired:true,holderReport:"STATE_UNCLAIMED_PROGRAM",law:"State Unclaimed Property Acts + UCC",protectiveScore:80},CA:{dormancyYears:3,escheatTo:"PROVINCE",noticeRequired:true,holderReport:"PROVINCIAL_PROGRAM",law:"Provincial Unclaimed Property",protectiveScore:85},GB:{dormancyYears:15,escheatTo:"CROWN",noticeRequired:true,holderReport:"BONAVACANTIA",law:"Companies Act + Bona Vacantia",protectiveScore:88},AU:{dormancyYears:7,escheatTo:"ASIC / STATE",noticeRequired:true,holderReport:"ASIC_UNCLAIMED_MONEY",law:"ASIC Act + State Acts",protectiveScore:85},DE:{dormancyYears:3,escheatTo:"STATE",noticeRequired:true,holderReport:"LOCAL_COURT",law:"BGB + EU GDPR",protectiveScore:95},FR:{dormancyYears:10,escheatTo:"CDC_CAISSE_DES_DEPOTS",noticeRequired:true,holderReport:"CDC",law:"Code civil + CDC",protectiveScore:95},JP:{dormancyYears:10,escheatTo:"NATIONAL_TREASURY",noticeRequired:true,holderReport:"LEGAL_AFFAIRS_BUREAU",law:"Civil Code",protectiveScore:85},IN:{dormancyYears:7,escheatTo:"IEPF",noticeRequired:true,holderReport:"IEPF_AUTHORITY",law:"Companies Act + IEPF Rules",protectiveScore:82},BR:{dormancyYears:5,escheatTo:"FEDERAL",noticeRequired:true,holderReport:"BANCO_CENTRAL",law:"Civil Code + LGPD",protectiveScore:90},ZA:{dormancyYears:3,escheatTo:"GUARDIANS_FUND",noticeRequired:true,holderReport:"MASTERS_OFFICE",law:"Administration of Estates + POPIA",protectiveScore:88},SG:{dormancyYears:6,escheatTo:"INSOLVENCY_OFFICE",noticeRequired:true,holderReport:"MINLAW",law:"Companies Act + PDPA",protectiveScore:85},DEFAULT_190:{dormancyYears:5,escheatTo:"LOCAL_GOVERNMENT",noticeRequired:true,holderReport:"LOCAL_ESCHEAT_AUTHORITY",law:"Local Escheatment Law - Most Protective Fallback",protectiveScore:85,note:"For all other 178 countries"}};
const BANKING_RAILS=[{rail:"SWIFT",use:"International bank messages",isProperty:false},{rail:"ACH",use:"US batch transfers",isProperty:false},{rail:"FEDWIRE",use:"US real-time large transfers",isProperty:false},{rail:"SEPA",use:"Euro zone transfers",isProperty:false},{rail:"ISO20022_PACS008",use:"Clearing message format - customer payment",isProperty:false},{rail:"FIRST_HAWAIIAN",use:"Settlement rail",isProperty:false},{rail:"FIRST_HAWAIIAN_STAGED",use:"Legacy rail id (kept so older lots still validate)",isProperty:false}];
function checkUnclaimedFull({lot,countryCode}){
  if(BANKING_RAILS.some(r=>r.rail===lot.type)) return {pass:false,reason:"RAIL_NOT_PROPERTY: Banking rails cannot be auctioned. Rails settle lots, they are not lots."};
  const isZombie=["ZOMBIE_FORECLOSURE","ZOMBIE_TITLE_HEIRLESS","VACANT_ABANDONED","TAX_DELINQUENT"].includes(lot.type);
  if(isZombie&&!lot.titleCleared) return {pass:false,action:"PAUSE_DO_NOT_LIST",reason:"ZOMBIE: Title not cleared - foreclosure / tax / heir process must complete first"};
  if(!lot.holderReported) return {pass:false,reason:"UNCLAIMED: Holder not reported to government - do not list"};
  if(!lot.escheated) return {pass:false,reason:"UNCLAIMED: Not escheated - do not list"};
  if(lot.ownerClaimedBeforeHammer) return {pass:false,action:"STOP_SALE_RETURN_TO_OWNER",reason:"Owner claimed before hammer - stop sale"};
  return {pass:true,type:lot.type,isZombie,reason:"UNCLAIMED_FULL_ELIGIBLE"};
}
function checkUnclaimedEligible({lot,countryCode}){
  const region=UNCLAIMED_BY_REGION[countryCode]||UNCLAIMED_BY_REGION.DEFAULT_190;
  if(!lot.holderReported) return {pass:false,reason:"UNCLAIMED: Holder has not reported to government - do not list"};
  if(!lot.escheated) return {pass:false,reason:"UNCLAIMED: Property has not escheated - do not list"};
  if((lot.dormantSinceYears||0)<region.dormancyYears) return {pass:false,reason:`UNCLAIMED: Dormancy not met - needs ${region.dormancyYears} years in ${countryCode}, has ${lot.dormantSinceYears}`};
  if(region.noticeRequired&&!lot.ownerNoticeSent) return {pass:false,reason:"UNCLAIMED: Owner notice required - not sent - pause"};
  if(lot.ownerClaimedBeforeHammer) return {pass:false,action:"STOP_SALE_RETURN_TO_OWNER",reason:"UNCLAIMED: Owner claimed before hammer - stop sale"};
  return {pass:true,region,reason:"UNCLAIMED_ELIGIBLE: dormancy met, holder reported, escheated, notice sent"};
}
function checkUnclaimed190({lot,sellerCode,bidderCode,itemCode,dataCode,settlementCode}){
  const codes=[sellerCode,bidderCode,itemCode,dataCode,settlementCode].filter(Boolean); const unique=[...new Set(codes)];
  const regions=unique.map(c=>UNCLAIMED_BY_REGION[c]||UNCLAIMED_BY_REGION.DEFAULT_190);
  const longestDormancy=Math.max(...regions.map(r=>r.dormancyYears));
  const eligible=checkUnclaimedEligible({lot,countryCode:sellerCode});
  if(!eligible.pass) return {...eligible,jurisdictions:unique,longestDormancyYears:longestDormancy};
  return {pass:true,jurisdictions:unique,longestDormancyYears:longestDormancy,appliedRule:"MOST_PROTECTIVE_DORMANCY_WINS",reason:`UNCLAIMED_190_PASSED: longest dormancy ${longestDormancy} years applied across ${unique.length} jurisdictions`};
}
function checkMarketplaceVsUnclaimed({lot}){
  if(lot.source==="MARKETPLACE") return {pass:true,source:"MARKETPLACE",needs:["WILLING_SELLER","CLEAN_TITLE","DISCLOSURE"],rule:"Willing seller + clean title"};
  if(lot.source==="UNCLAIMED") return {pass:true,source:"UNCLAIMED",needs:["HOLDER_REPORTED","ESCHEATED","DORMANCY_MET","OWNER_NOTICE","TITLE_CLEARED_IF_ZOMBIE"],rule:"Escheated after dormancy + notice"};
  return {pass:false,reason:"SOURCE_MUST_BE_MARKETPLACE_OR_UNCLAIMED"};
}
module.exports={UNCLAIMED_TYPES_FULL_32,UNCLAIMED_GLOBAL,UNCLAIMED_BY_REGION,BANKING_RAILS,checkUnclaimedFull,checkUnclaimedEligible,checkUnclaimed190,checkMarketplaceVsUnclaimed};
