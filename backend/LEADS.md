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
