# Property lead pipeline + Reply.io / Jason AI webhooks (live)

Everything below is admin-only (log in as an admin, send the bearer token). API prefix is
`/api/v1` unless you changed it. Tables (`property_leads`, `outreach_events`) are created
automatically at startup. There is nothing to buy: the pipeline works on records you feed it.

## 1. Bring in properties
Three ways, all return counts of inserted / updated / rejected (with reasons).

* **Free open-data portals** (Socrata county/city/state portals):
  `POST /leads/import-open-data`
  `{"domain":"data.example.gov","dataset_id":"abcd-1234","where":"amount_due > 1000","limit":5000,
    "mapping":{"owner_name":"taxpayer","address":"situs","amount_owed":"amount_due","flags":"status"}}`
  `mapping` is {our field: their column}. Common column names are recognized without a mapping.
* **CSV file:** `POST /leads/import-csv` `{"csv_text":"<whole file text>","source":"county-x"}`
* **JSON rows:** `POST /leads/import` `{"records":[{...}],"source":"partner"}`

Max 5,000 rows per call; repeat with `offset` to page a large portal. Same property seen twice is
merged (parcel id, or address+city+state+zip), never duplicated.

## 2. What the engine does to each row
Cleans address/state/zip/phone/email; marks `absentee_owner`, `out_of_state_owner`, `high_equity`
from the fields; reads distress from your `flags` column (tax_delinquent, pre_foreclosure, probate,
unclaimed_funds, code_violation, lien, vacant); scores 0-100 (reasons are in `lead_engine.score_lead`).
Nothing is guessed: a field the source did not supply stays empty, and an amount alone is not labelled
tax or surplus unless the source says so.

## 3. Find and export
`GET /leads?states=HI&states=CA&min_score=40&all_flags=tax_delinquent&any_flags=probate&any_flags=vacant&has_email=true`
`GET /leads/export.csv?...same filters...`
`PATCH /leads/{id}/status` with `new | contacted | onboarded | do_not_contact`.

## 4. Send to outreach
`POST /leads/push-outreach` `{"campaign_id":"<real Reply.io campaign id>","min_score":40,"limit":200}`
Only new leads with an email; opted-out emails are skipped; a lead is marked `contacted` only after
Reply.io accepted it; stops after 5 Reply.io failures. Jason AI works the replies inside Reply.io.

## 5. Reply.io webhooks (replies, bounces, opt-outs)
1. In Render set `REPLY_IO_WEBHOOK_SECRET` to a long random string (40+ characters) and redeploy.
2. `POST /outreach/webhooks/subscribe` `{"base_url":"https://<your public https address>"}`
   creates the Reply.io subscriptions pointing at `/outreach/webhooks/reply/<secret>`.
3. `GET /outreach/events` shows what Reply.io has sent. Opt-outs block that email everywhere
   (`/outreach/contacts` and `/leads/push-outreach` return/skip it).
4. `GET /outreach/webhooks/events`, `POST /outreach/webhooks/{id}/test`, `GET /outreach/webhooks/{id}/logs`
   are Reply.io's own list / test / failed-delivery log.

Reply.io's documentation does not describe webhook signing, so the secret in the address is the only
protection; keep it private. It also does not publish the event layout, so the email is found by searching
the payload; events with no findable email are stored but cannot block anyone.

## Limits
* The data is whatever the sources give you; this does not contain a nationwide property database.
* Owner emails/phones exist only if a source supplied them. Without an email a lead cannot go to Reply.io.
* Jason AI's approval queue and sequence building stay inside Reply.io (no documented API paths).

## 6. Continuous search - 24/7, follows the sun
The platform runs a lead worker all day, every day (it starts with the platform; `LEAD_LOOP_ENABLED=true`
by default; `LEAD_LOOP_INTERVAL_SECONDS` default 600). Tell it where to look with one Render environment
variable, `LEAD_SOURCES_JSON` - a JSON list, one entry per open-data table:

```
[{"name":"norfolk-tax","domain":"data.norfolk.gov","dataset_id":"7qie-z5gv","timezone":"America/New_York",
  "page_size":2000,"flags":"tax_delinquent",
  "mapping":{"owner_name":"owner_name","address":"address","amount_owed":"total"}},
 {"name":"richmond-tax","domain":"data.richmondgov.com","dataset_id":"83t5-hbac","timezone":"America/New_York",
  "page_size":2000,"flags":"tax_delinquent",
  "mapping":{"owner_name":"current_owner_name_1","parcel_id":"property_code","amount_owed":"total_due"}}]
```
* `timezone` = where that source's region is. The source is worked while it is daytime there, so as the
  sun moves, the worker is always working a region in daylight. Leave it out to work a source around the clock.
* Each cycle keeps pulling the next `page_size` rows (up to 50 pages or ~7 minutes per source) until the table is done, cleans/dedupes/scores them into the lead table and remembers its
  place (survives restarts). At the end of a table it starts over on the next daytime pass to catch new records.
* `flags` stamps every row from that source (use it when the table is, say, all tax-delinquent).
* One broken source never stops the rest. `GET /leads/sources/status` shows each source, whether it is working
  now, its place, and its last result or error.
* Add more sources by editing `LEAD_SOURCES_JSON` and redeploying. A source needs a real Socrata table:
  find one on the portal's page for the dataset (the `abcd-1234` id in its address).

### Nothing skipped silently
* Pages are read in a fixed order (`$order=:id`), so the portal cannot repeat or skip rows between pages.
* Several rows for the same property (years, installments) are added into one lead's `amount_owed`.
* A row is rejected only if it has neither a street address nor a parcel id. Every import and every worker pass
  reports `received`, `distinct_properties` and `rejected` with the reasons; see `last_result` in `GET /leads/sources/status`.
  If a portal's rejected count is high, its column names need a `mapping` entry.

## 7. Revenue ranking
Every lead carries `est_revenue` (and a `revenue` breakdown): Stage A = the unclaimed amount held for the owner
(100% to Pacific Rim Auctions / TerraRoots), Stage B = 3% of assessed value (low end of your 3-5% scale). These are
estimates from the record's own numbers, not forecasts. `GET /leads`, `/leads/export.csv` and
`POST /leads/push-outreach` all work the highest `est_revenue` first, so outreach capacity goes to the biggest
opportunities first. Leads whose records have neither an amount nor an assessed value rank last.

## 8. Expired claim deadlines (re-checked every pass)
A row whose source says the claim deadline has expired / claims will not be accepted is flagged `claims_expired`.
It stays in the table, and the worker re-reads its source every pass: if the source later re-lists it without that
wording (a reopened or new deadline), the flag clears and the lead becomes claimable again, with its Stage A
revenue estimate back. While flagged, `push-outreach` holds it (`held_claims_expired`) and Stage A counts 0.
What happens to money after a deadline is each jurisdiction's law, not this code: Kauai's own listing says
"DEADLINE FOR CLAIMS HAS EXPIRED. CLAIMS WILL NOT BE ACCEPTED." and refers to KCC Sec. 5A-5.9, whose text I could
not retrieve. Get that section (rpc@kauai.gov, 808-241-4272) or run the country legal-review draft
(`POST /legal-review/draft/{node_id}`, needs OPENAI_API_KEY) for each country before relying on expired funds.

`push-outreach` takes `"include_claims_expired": true` to contact `claims_expired` leads as well (default false).
Your campaign text decides what owners are told; the county's listing for those says claims will not be accepted.

## 9. Other countries (CKAN portals) - the sun keeps moving
Besides Socrata, the worker reads CKAN portals (Australia, Canada, UK, EU and many more). Entry shape:
`{"name":"qld-unclaimed","type":"ckan","domain":"www.data.qld.gov.au","resource_id":"<dataset resource UUID>",
  "timezone":"Australia/Brisbane","page_size":2000,"flags":"unclaimed_funds","mapping":{...}}`
The resource must be datastore-enabled (its page shows an API / "Data API" button). Datasets that looked like fits
(columns NOT yet checked, so first look at `rejected_reasons` in `GET /leads/sources/status` and add a `mapping`):
Queensland unclaimed monies `872065ae-ddfd-4b5f-ad15-e1935dadd883` (data.qld.gov.au), Victoria unclaimed money claims
`6d9458b5-a448-454c-a559-f368c36ec674` (discover.data.vic.gov.au), Canada unclaimed estate or trust funds
`42006fa6-5068-4dfe-ba63-037c0fe1fa65` (open.canada.ca/data). Each source is worked only while its `timezone` is
in daylight, so as Kauai goes dark the worker is already on Asia-Pacific, then Europe, then the Americas.

## 10. Closed-claim leads are hidden
Leads whose source says the claim deadline has passed (`claims_expired`) no longer appear in `GET /leads`,
`/leads/export.csv` or outreach. They are still re-read each pass by the worker; if a source re-lists them with
an open deadline the flag clears and they appear again at once. `GET /leads/sources/status` shows how many are
hidden (`hidden_claims_closed`). Only `push-outreach` with `"include_claims_expired": true` brings them back.

## 11. Why nothing could go live (fixed) - read this
A listing could only be created from an asset whose `do_no_harm_cleared` and `jurisdiction_cleared` were both
"cleared", and no code ever set either (they started "pending" forever), so no auction could open anywhere.
* `jurisdiction_cleared` is now derived when a listing is created: it is "cleared" exactly when that country's
  jurisdiction node is ACTIVE (set by a named human at `PATCH /jurisdiction-nodes/{id}/review`). Nothing else changes
  about legal review.
* `PATCH /assets/{asset_id}/do-no-harm` (admin or compliance officer, named `reviewed_by`, audited) records the
  Do No Harm result: `{"do_no_harm_cleared":"cleared","reviewed_by":"<name>","notes":"..."}`.
Per property, the path to a live auction is now: asset VERIFIED -> Do No Harm cleared (above) -> country node ACTIVE
-> create listing -> lawful basis recorded -> for real property, the three inspections disclosed -> daily recheck
publishes it. The country nodes are the biggest lever: until a node is ACTIVE, every asset from that country waits.
`GET /jurisdiction-nodes/coverage` shows how many are ACTIVE.
