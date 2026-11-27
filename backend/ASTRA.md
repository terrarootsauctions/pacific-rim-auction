# Astra legal tools - live setup

Two live endpoints that use OpenAI GPT-6 Astra to help with legal review. Both are advisory:
a named person still verifies and signs. Both refuse (HTTP 503) until configured.

## Switch on (Render > pacific-rim-auctions > Environment)
| Variable | Value |
|---|---|
| `OPENAI_API_KEY` | your OpenAI API key (keep it secret) |
| `ASTRA_MODEL` | `gpt-6-astra` (confirm the id in your OpenAI account) |
| `ASTRA_REASONING_EFFORT` | optional: low, medium, high (default), xhigh, max |
| `ASTRA_WEB_SEARCH` | optional: true (default) or false |

Save. Render redeploys. When OpenAI opens Astra for Law to your account, change `ASTRA_MODEL` to what they give you; no code change.

## 1. Draft a jurisdiction's legal research
`POST /api/v1/legal-review/draft/{node_id}` (log in as admin or compliance; Bearer token)
Returns a packet. Astra uses live web search; a web address is kept only if the search returned it. It never sets the status, reviewer name, attestation or retrieved date.
Then: open every source, confirm it supports the finding, fill in `retrieved_on`, `recommended_status`, `reviewer_name`, `reviewer_attests: true`, send to `POST /legal-review/check`, and submit the returned payload to `PATCH /jurisdiction-nodes/{id}/review`.

## 2. Check a document against statements
`POST /api/v1/legal-review/document-check`
```json
{ "document_text": "<full text of the deed or agreement>",
  "statements": ["The seller holds title to 12 Kauai Road."],
  "confirm_send_to_provider": true,
  "reference": "listing-or-claim-id" }
```
Each statement comes back supported / not_supported / unclear. "supported" always carries a quote that the platform has verified word for word in your document; otherwise it is downgraded to unclear. It records nothing and never marks title. Read the quoted passage in the original before relying on it.

## Notes
- Only the country code, name and region are sent for drafting. Document text is sent only for document-check, and only when `confirm_send_to_provider` is true.
- Every use is written to the audit log (no document text in it).
- Billing is by OpenAI per use. Ask OpenAI about Zero Data Retention for your account before sending sensitive documents.
