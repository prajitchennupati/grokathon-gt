Cached Grok responses, one JSON file per (task, demo key). Written automatically the first time a
live call succeeds, or all at once with `make precache` (needs `XAI_API_KEY`). With `--offline`
(or when the API fails) the app reads these before falling back to deterministic templates.
