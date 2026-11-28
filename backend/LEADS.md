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
