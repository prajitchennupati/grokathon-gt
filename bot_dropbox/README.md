Grok Bots that can write files but not call webhooks drop `.json` files here
(same shape as `POST /api/bots/{role}/inbox`). Processed files move to `processed/`,
invalid ones to `rejected/`.
