<!-- Shared footer appended to every role file by the app (GET /api/grokbot/{role}.md). -->
## How to deliver your work

Post exactly one JSON object per finished task. **Option A — webhook (preferred):**

```
POST {{PUBLIC_BASE_URL}}/api/bots/{{ROLE}}/inbox
Content-Type: application/json
X-Clearance-Token: {{CLEARANCE_TOKEN}}
```

**Option B — shared folder:** if you cannot make HTTP requests, save the same JSON as a
`.json` file in the shared Clearance folder (`bot_dropbox/`). The app picks it up within 2 s;
bad files are moved to `bot_dropbox/rejected/` with the reason.

JSON shape (all fields are validated; unknown roles or empty titles/bodies are rejected):

```json
{
  "role": "{{ROLE}}",
  "kind": "<short_snake_case_kind>",
  "title": "<one line, max 200 chars>",
  "body_markdown": "<your output as Markdown>",
  "proposed_actions": [
    {"type": "send_message | file_report | other", "summary": "<one line>", "to": "<recipient or null>", "body": "<full text>"}
  ],
  "sources": [{"title": "<page title>", "url": "<https://...>"}]
}
```

A `201` response with `output_id` means it was received. `401` = wrong token, `422` = the JSON did not
match the shape above (the response says which field).

## Situation data

The app's live picture is available at:

```
GET {{PUBLIC_BASE_URL}}/api/bots/{{ROLE}}/context
X-Clearance-Token: {{CLEARANCE_TOKEN}}
```

When the app needs you it also writes a task card to `bot_dropbox/tasks/{{ROLE}}-T<sim seconds>.json`
with the context and inbox URLs. Watch that folder, or check the context endpoint when asked.

## Hard rules

- This is an **advisory prototype — not for operational use**. Never contact a real ATC facility,
  airline, pilot or FAA system. Never send real messages. Everything you propose goes in
  `proposed_actions` and a human approves it; approval is simulated in the app.
- Use only facts from the pages you read or the context endpoint. Do not invent aircraft, times,
  NOTAMs or numbers. If a source is down, say so in the output and continue with what you have.
- Cite every web page you used in `sources`.
- Keep it short: controllers read this between transmissions.
