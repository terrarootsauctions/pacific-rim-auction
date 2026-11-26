# Payloads - every gate fails closed. Pause = the gate worked.

Every action runs: SI token > permission/kill switch > 190-country law > UCC 2-328 + Hawaii > asset universe > source routing > unclaimed rules (if source=UNCLAIMED) > all legalities > Hawaii license > shill checks > audit entry. If anything fails, read `checks` for `ok:false`, fix that field, retry.

## Grant permission (once; /admin does this for you)
POST /api/permission
{ "mode":"EXECUTE", "actionType":"ALL", "limit":null, "jurisdiction":"ALL", "expiresAt":"2027-01-01T00:00:00Z" }
`expiresAt` is required and must be in the future. `mode:"OVERSEE"` means every action must also carry `"siApproved":true`.

## 1. Create lot - POST /api/lots
{
  "title":"Waimea House", "description":"From source docs", "category":"REAL_ESTATE", "sellerId":"SELLER-1",
  "reserveStatus":"WITH_RESERVE", "reservePrice":100000, "startingPrice":90000, "jurisdictions":["US"],
  "sellerCode":"US", "itemCode":"US", "dataCode":"US", "settlementCode":"US",
  "getLicense":true, "hrs467Compliant":true, "realEstateLicense":true, "realEstateLicenseChecked":true,
  "source":"MARKETPLACE", "type":"SINGLE_FAMILY", "isPhysical":true,
  "reserveDisclosed":true, "conditionDisclosed":true, "provenanceChecked":true, "feesDisclosed":true,
  "buyerPremium":0.10, "sellerCommission":0.05, "sellerIdentityDisclosed":true, "totalPriceDisclosed":true,
  "titleDisclosed":true, "lienDisclosed":true, "taxDisclosed":true, "hazardDisclosed":true, "agencyDisclosed":true,
  "seller": { "id":"SELLER-1", "kycPassed":true, "kycReference":"<provider reference>" }
}
NEW vs old: `seller.kycReference` required; all four country codes required (none assumed); `source` required (MARKETPLACE or UNCLAIMED); no buyer needed to create a lot; `rail`/`escrow` are NOT sent here any more.

UNCLAIMED adds: `"source":"UNCLAIMED","type":"DORMANT_BANK_ACCOUNT","holderReported":true,"escheated":true,"dormantSinceYears":6,"ownerNoticeSent":true,"ownerClaimedBeforeHammer":false` (zombie types also `"titleCleared":true`).
Mine: `permits`, `mineralRightsTitle`. Jet: `airworthiness`, `registrationCleared`. Yacht/ship: `flagRegistrationCleared`. Trust: `inTrust`, `trusteeAuthorized`, `trustee:{authorized:true}`.

## 2. Bid - POST /api/lots/:id/bid
{ "bidderId":"BUYER-1", "amount":110000, "bidderCode":"US", "buyer": { "id":"BUYER-1", "kycPassed":true, "kycReference":"<provider reference>" } }
Amount must be a positive number above the starting price and above the current high bid. Seller (or related) bidding is blocked.

## 3. Close - POST /api/lots/:id/close   (body `{}`)
Highest bid wins if the reserve is met.

## 4. Settle - POST /api/lots/:id/settle
{ "rail":"FIRST_HAWAIIAN", "escrowReference":"<escrow reference>" }
Allowed rails: SWIFT, ACH, FEDWIRE, SEPA, ISO20022_PACS008, FIRST_HAWAIIAN, FIRST_HAWAIIAN_STAGED (legacy id), TRUST_RAIL, ESCROW_RAIL. Buyer KYC comes from the winning bid.

## Dry run - POST /api/check
Same lot payload (add `"actionType":"PLACE_BID"` + `"bid":{...}` to test other stages). Writes nothing.
