# Security notes (this deployment)

- Blueprint gates stay on: fencing, cart provenance, merchant staging provenance, host approval, memory validation.
- No payment in the agent. Checkout is a Shopware `continue_url` handoff. `complete_checkout` is off by default.
- Merchant `stage_*` does not call Admin writes. Apply is `POST /api/merchant/changes/{id}/apply` after the host marks the change approved.
- Tokens (Admin, Store API, optional Identity Linking) stay on the server. They are never tool arguments or log lines.
- Local UCP `signature-policy=log` accepts unsigned requests so Docker works without RFC 9421. Production must switch to `strict` and set `UCP_AGENT_SIGNING_KEY_PEM_FILE`.
- `SWAG_AGENTIC_COMMERCE_UCP_PROFILE_FETCHING_DEVELOPMENT_MODE=1` is local-only (http agent profiles). Do not enable on a public shop.
- CORS is loopback-only via `demo_common` host middleware.
- Identity Linking is optional; without client credentials every session is a guest.
