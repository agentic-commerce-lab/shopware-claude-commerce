# Merchant agent

FastAPI host implementing Anthropic `MerchantBackend` against Shopware Admin REST. Writes are staged in an in-memory ledger; only `POST /api/merchant/changes/{id}/apply` mutates the shop (after host approval).

## Run

```bash
# credentials from docker/.generated.env + admin user/password
uvicorn merchant.api.main:app --port 8005
```

`SHOPWARE_LOCAL_STORE=1` uses `data/seed.json` (no live Admin API). Health still starts if credentials are missing and tells you what to set.

## Safety

- `stage_*` never calls Admin PATCH (proven in `api/tests/test_staging.py`)
- Apply re-checks guardrails, writes, then marks the ledger applied
- A failed write leaves the change staged
- Campaigns are not applied (`ChangeNotApplicable`)
- Promotions stay ledger-only in this version
- Admin MCP `dryRun=true` is used for previews when `SHOPWARE_ADMIN_TRANSPORT=mcp`

## Verify

```bash
pytest merchant/api/tests
python merchant/scripts/smoke_live.py --read-only
```
