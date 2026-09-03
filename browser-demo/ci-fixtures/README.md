# CI seed fixtures

GitHub-hosted runners hit PHP WASM traps during Shopware installer migrations. The Pages workflow copies these files into the playground bundle so `prepare-shop.mjs` skips the in-WASM install (same seeded catalog, plugins, and demo credentials as a local `prepare-shop`).

Regenerate when bootstrap, plugins, or seed scripts change:

```bash
cd browser-demo
FORCE_INSTALL=1 node build/prepare-shop.mjs
cp playground/public/versions/6.7.13.1/shopware.sql.gz ci-fixtures/6.7.13.1/
cp app/public/demo/shop-config.json ci-fixtures/6.7.13.1/
```

`shop-config.json` holds **demo-only** integration/handoff values for the public WASM shop, not production secrets.
