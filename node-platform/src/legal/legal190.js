
// PACIFIC RIM AUCTIONS - 190 COUNTRIES - WIRED - CommonJS
const TOTAL_COUNTRIES = 190;
const COVERAGE = '190_COUNTRIES_6_CONTINENTS_24_7_365';
// Full list is generated: specific rules for key jurisdictions, fallback for rest.
// Fallback = most protective: HIGH disclosure, 14d cooling, score 85.
const SPECIFIC = {
 AU:{auctionLaw:"Australian Consumer Law",dataLaw:"Privacy Act 1988",coolingOffDays:0,protectiveScore:85,notes:"ACL guarantees. State auctioneer licensing varies."},
 BR:{auctionLaw:"Civil Code + CDC",dataLaw:"LGPD",coolingOffDays:7,protectiveScore:90,notes:"LGPD similar to GDPR. 7-day regret."},
 CA:{auctionLaw:"Provincial Sale of Goods + Consumer Protection",dataLaw:"PIPEDA + Provincial",coolingOffDays:10,protectiveScore:88,notes:"PIPEDA. Quebec Civil Code differs."},
 FR:{auctionLaw:"Code civil + Code de commerce",dataLaw:"EU GDPR + CNIL",coolingOffDays:14,protectiveScore:95,notes:"EU GDPR. Droit de retractation."},
 DE:{auctionLaw:"BGB + GewO",dataLaw:"EU GDPR",coolingOffDays:14,protectiveScore:95,notes:"EU GDPR most protective. Widerrufsrecht 14 days."},
 IN:{auctionLaw:"Sale of Goods Act 1930 + Consumer Protection Act 2019",dataLaw:"DPDP Act 2023",coolingOffDays:0,protectiveScore:82,notes:"DPDP. Consumer forums."},
 JP:{auctionLaw:"Civil Code + Consumer Contract Act",dataLaw:"APPI",coolingOffDays:8,protectiveScore:85,notes:"APPI data law."},
 SG:{auctionLaw:"Sale of Goods Act",dataLaw:"PDPA",coolingOffDays:0,protectiveScore:85,notes:"PDPA consent required."},
 ZA:{auctionLaw:"Consumer Protection Act",dataLaw:"POPIA",coolingOffDays:5,protectiveScore:88,notes:"POPIA. CPA cooling off."},
 CH:{auctionLaw:"Code of Obligations",dataLaw:"nDSG / FADP",coolingOffDays:14,protectiveScore:92,notes:"Revised FADP."},
 AE:{auctionLaw:"Civil Transactions Law + Federal Decree",dataLaw:"Federal PDPL",coolingOffDays:0,protectiveScore:80,notes:"PDPL. DIFC/ADGM separate."},
 GB:{auctionLaw:"Sale of Goods Act + Consumer Rights Act",dataLaw:"UK GDPR + Data Protection Act",coolingOffDays:14,protectiveScore:90,notes:"14-day cooling off for distance sales. Auctioneer must disclose reserve."},
 US:{auctionLaw:"UCC 2-328",dataLaw:"State privacy + FTC",coolingOffDays:0,protectiveScore:80,notes:"With reserve default. Shill bidding blocked. Hawaii: HRS 237-9 GET, 445 county, 467 real estate, 437 motor vehicle."},
};
const ALL_CODES = ["AF","AL","DZ","AD","AO","AG","AR","AM","AU","AT","AZ","BS","BH","BD","BB","BY","BE","BZ","BJ","BT","BO","BA","BW","BR","BN","BG","BF","BI","KH","CM","CA","CV","CF","TD","CL","CN","CO","KM","CG","CD","CR","CI","HR","CU","CY","CZ","DK","DJ","DM","DO","EC","EG","SV","GQ","ER","EE","SZ","ET","FJ","FI","FR","GA","GM","GE","DE","GH","GR","GD","GT","GN","GW","GY","HT","HN","HU","IS","IN","ID","IR","IQ","IE","IL","IT","JM","JP","JO","KZ","KE","KI","KW","KG","LA","LV","LB","LS","LR","LY","LI","LT","LU","MG","MW","MY","MV","ML","MT","MH","MR","MU","MX","FM","MD","MC","MN","ME","MA","MZ","MM","NA","NR","NP","NL","NZ","NI","NE","NG","MK","NO","OM","PK","PW","PA","PG","PY","PE","PH","PL","PT","QA","RO","RU","RW","KN","LC","VC","WS","SM","ST","SA","SN","RS","SC","SL","SG","SK","SI","SB","SO","ZA","SS","ES","LK","SD","SR","SE","CH","SY","TJ","TZ","TH","TG","TO","TT","TN","TR","TM","TV","UG","UA","AE","GB","US","UY","UZ","VU","VE","VN","YE","ZM","ZW"];
const NAMES={AF:"Afghanistan",AL:"Albania",DZ:"Algeria",AD:"Andorra",AO:"Angola",AG:"Antigua and Barbuda",AR:"Argentina",AM:"Armenia",AU:"Australia",AT:"Austria",AZ:"Azerbaijan",BS:"Bahamas",BH:"Bahrain",BD:"Bangladesh",BB:"Barbados",BY:"Belarus",BE:"Belgium",BZ:"Belize",BJ:"Benin",BT:"Bhutan",BO:"Bolivia",BA:"Bosnia and Herzegovina",BW:"Botswana",BR:"Brazil",BN:"Brunei",BG:"Bulgaria",BF:"Burkina Faso",BI:"Burundi",KH:"Cambodia",CM:"Cameroon",CA:"Canada",CV:"Cabo Verde",CF:"Central African Republic",TD:"Chad",CL:"Chile",CN:"China",CO:"Colombia",KM:"Comoros",CG:"Congo",CD:"Congo Democratic Republic",CR:"Costa Rica",CI:"Cote d'Ivoire",HR:"Croatia",CU:"Cuba",CY:"Cyprus",CZ:"Czechia",DK:"Denmark",DJ:"Djibouti",DM:"Dominica",DO:"Dominican Republic",EC:"Ecuador",EG:"Egypt",SV:"El Salvador",GQ:"Equatorial Guinea",ER:"Eritrea",EE:"Estonia",SZ:"Eswatini",ET:"Ethiopia",FJ:"Fiji",FI:"Finland",FR:"France",GA:"Gabon",GM:"Gambia",GE:"Georgia",DE:"Germany",GH:"Ghana",GR:"Greece",GD:"Grenada",GT:"Guatemala",GN:"Guinea",GW:"Guinea-Bissau",GY:"Guyana",HT:"Haiti",HN:"Honduras",HU:"Hungary",IS:"Iceland",IN:"India",ID:"Indonesia",IR:"Iran",IQ:"Iraq",IE:"Ireland",IL:"Israel",IT:"Italy",JM:"Jamaica",JP:"Japan",JO:"Jordan",KZ:"Kazakhstan",KE:"Kenya",KI:"Kiribati",KW:"Kuwait",KG:"Kyrgyzstan",LA:"Laos",LV:"Latvia",LB:"Lebanon",LS:"Lesotho",LR:"Liberia",LY:"Libya",LI:"Liechtenstein",LT:"Lithuania",LU:"Luxembourg",MG:"Madagascar",MW:"Malawi",MY:"Malaysia",MV:"Maldives",ML:"Mali",MT:"Malta",MH:"Marshall Islands",MR:"Mauritania",MU:"Mauritius",MX:"Mexico",FM:"Micronesia",MD:"Moldova",MC:"Monaco",MN:"Mongolia",ME:"Montenegro",MA:"Morocco",MZ:"Mozambique",MM:"Myanmar",NA:"Namibia",NR:"Nauru",NP:"Nepal",NL:"Netherlands",NZ:"New Zealand",NI:"Nicaragua",NE:"Niger",NG:"Nigeria",MK:"North Macedonia",NO:"Norway",OM:"Oman",PK:"Pakistan",PW:"Palau",PA:"Panama",PG:"Papua New Guinea",PY:"Paraguay",PE:"Peru",PH:"Philippines",PL:"Poland",PT:"Portugal",QA:"Qatar",RO:"Romania",RU:"Russia",RW:"Rwanda",KN:"Saint Kitts and Nevis",LC:"Saint Lucia",VC:"Saint Vincent and the Grenadines",WS:"Samoa",SM:"San Marino",ST:"Sao Tome and Principe",SA:"Saudi Arabia",SN:"Senegal",RS:"Serbia",SC:"Seychelles",SL:"Sierra Leone",SG:"Singapore",SK:"Slovakia",SI:"Slovenia",SB:"Solomon Islands",SO:"Somalia",ZA:"South Africa",SS:"South Sudan",ES:"Spain",LK:"Sri Lanka",SD:"Sudan",SR:"Suriname",SE:"Sweden",CH:"Switzerland",SY:"Syria",TJ:"Tajikistan",TZ:"Tanzania",TH:"Thailand",TG:"Togo",TO:"Tonga",TT:"Trinidad and Tobago",TN:"Tunisia",TR:"Turkiye",TM:"Turkmenistan",TV:"Tuvalu",UG:"Uganda",UA:"Ukraine",AE:"United Arab Emirates",GB:"United Kingdom",US:"United States",UY:"Uruguay",UZ:"Uzbekistan",VU:"Vanuatu",VE:"Venezuela",VN:"Vietnam",YE:"Yemen",ZM:"Zambia",ZW:"Zimbabwe"};
const COUNTRIES_190 = ALL_CODES.map(code=>{
  const s=SPECIFIC[code];
  if(s) return {code,name:NAMES[code],...s,disclosure:"HIGH"};
  return {code,name:NAMES[code],auctionLaw:"Civil Code / Sale of Goods - Local",dataLaw:"Local Data Protection - Most Protective Fallback",disclosure:"HIGH",coolingOffDays:14,protectiveScore:85,notes:"Fallback: Apply most protective rule. If local law requires disclosure and another forbids it, PAUSE and escalate to SI."};
});
function getCountry(code){return COUNTRIES_190.find(c=>c.code===code)||null;}
function getMostProtectiveRule(codes){const rules=codes.map(getCountry).filter(Boolean); if(!rules.length) return {pass:false,reason:'NO_JURISDICTIONS_DETECTED - pause'}; const sorted=[...rules].sort((a,b)=>b.protectiveScore-a.protectiveScore); return {pass:true,applied:sorted[0],all:rules,rule:'MOST_PROTECTIVE_RULE_WINS'};}
function check190Countries({sellerCode,bidderCode,itemCode,dataCode,settlementCode,requireBidder=false}){
  const required={sellerCode,itemCode,dataCode,settlementCode}; if(requireBidder) required.bidderCode=bidderCode;
  const missing=Object.keys(required).filter(k=>!required[k]);
  if(missing.length) return {pass:false,reason:'LOCATION_CODES_MISSING: '+missing.join(', ')+' - every location must be stated, none are assumed'};
  const codes=[sellerCode,bidderCode,itemCode,dataCode,settlementCode].filter(Boolean);
  const unique=[...new Set(codes)];
  const unknown=unique.filter(c=>!getCountry(c));
  if(unknown.length) return {pass:false,reason:'UNKNOWN_COUNTRY_CODE: '+unknown.join(', ')+' - not one of the 190 covered countries'};
  const rules=unique.map(getCountry);
  const withForbids=rules.filter(r=>r.forbidsDisclosure);
  const requires=rules.filter(r=>r.disclosure==='HIGH');
  if(requires.length&&withForbids.length) return {pass:false,action:'PAUSE_PRESERVE_ESCALATE_TO_SI',conflict:{requires,forbids:withForbids},reason:'LAW_CONFLICT: one land requires disclosure, another forbids it'};
  const mostProtective=getMostProtectiveRule(unique);
  return {pass:true,jurisdictions:unique,countries:rules,mostProtective:mostProtective.applied,coolingOffDaysApplied:Math.max(...rules.map(r=>r.coolingOffDays||0)),rule:'190_COUNTRIES_CHECK_PASSED - MOST_PROTECTIVE_APPLIED',disclosure:'HIGH - Disclose reserve, condition, provenance, fees, identity of seller type'};
}
function checkShill190({lot,bidder,seller}){
  if(bidder.id===seller.id||bidder.relatedToSeller){
    if(!(lot.disclosedReserveBidding===true&&lot.reserveBiddingAllowed===true)) return {pass:false,action:'BLOCK_BID_PAUSE_LOT_ESCALATE_TO_SI',reason:'SHILL_BLOCKED_ALL_190_COUNTRIES'};
  }
  return {pass:true,reason:'SHILL_CHECK_OK_190'};
}
function checkUCCAndLocal({lot,countryCode}){const country=getCountry(countryCode);const isUS=countryCode==='US';return {country,usRule:isUS?'UCC 2-328: Each lot separate sale. With reserve unless explicitly without reserve. Fall of hammer completes.':null,localRule:country?.auctionLaw,withReserveDefault:true,mustDiscloseReserve:true};}
const LEGAL_190={total:190,principle:'Abide by laws of every country we come upon. Do no harm. Self heal. Self improve.',precedence:['MANDATES','ADDENDUM_LEGAL','PERMISSION','TRANSACTION_WORK']};
module.exports={TOTAL_COUNTRIES,COVERAGE,COUNTRIES_190,getCountry,getMostProtectiveRule,check190Countries,checkShill190,checkUCCAndLocal,LEGAL_190};
