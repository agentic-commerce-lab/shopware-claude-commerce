# Docker Shopware

Local Shopware 6.7 used by the shopping and merchant agents.

## Image choice

**`dockware/shopware:6.7.13.0`** — a single container with Shopware already installed, MariaDB, and a demo catalog. It has `linux/arm64` and `linux/amd64` tags, so it boots on Apple Silicon without qemu.

We did **not** use:

- `shopware/docker-dev` / `new-shopware-setup` — generates a project from scratch; slower to first HTTP 200.
- Official `ghcr.io/shopware/docker-base` — production PHP image without Shopware; you bring the project.
- Deprecated `dockware/play` / `dockware/dev` — superseded by `dockware/shopware`.

Pinned to **6.7.13.0** (latest dockware 6.7 tag at time of writing). Masterplan target is 6.7.14+; 6.7.13 still has the `MCP_SERVER` feature flag, which bootstrap enables. REST UCP works regardless.

## Ports and credentials

| What | Value |
|---|---|
| Storefront | http://localhost:8080 |
| Admin | http://localhost:8080/admin |
| Admin login | `admin` / `shopware` |
| MySQL | `localhost:3306`, `root` / `root`, database `shopware` |
| UCP discovery | http://localhost:8080/.well-known/ucp |

## Run

From the repo root:

```bash
docker compose -f docker/compose.yaml up -d
./docker/bootstrap.sh
```

Bootstrap clones `SwagAgenticCommerce` into the container, installs `ucp-php-sdk`, activates the plugin, installs `CommerceAgentsHandoff` (checkout token adopt), exposes UCP on the Storefront sales channel (`signature-policy=log`), generates signing keys, seeds extra catalog rows, and writes `docker/.generated.env`.

If GitHub/Packagist cannot install the plugin, Shopware still runs. The storefront backend then uses the Store API fallback (documented in `docs/shopware-mapping.md`).

## Commands inside the shop

```bash
docker exec -u www-data commerce-agents-shopware bash -c 'php /var/www/html/bin/console plugin:list'
docker exec -u www-data commerce-agents-shopware bash -c 'php /var/www/html/bin/console ucp:channels'
docker exec -u www-data commerce-agents-shopware bash -c 'php /var/www/html/bin/console ucp:config:show --sales-channel=Storefront'
```

Until bootstrap rewrites `sales_channel_domain` to `http://localhost:8080`, the storefront `/` returns HTTP 400 (domain mapping). Admin API (`/api/_info/version` → 401) is the health signal. Bootstrap waits for MySQL as well as PHP.

## Local UCP agent profile

Shopware fetches the `UCP-Agent` profile URL **from inside the container**. `http://localhost:8080` is the published host port and is unreachable from Apache (port 80). Bootstrap copies repo `agent-profile.json` to `/var/www/html/public/agent-profile.json` and sets `UCP_AGENT_PROFILE_URL=http://localhost/agent-profile.json`.

Do **not** bind-mount that file: dockware `chown`s `public/` on boot and a read-only mount exits the container.

Compose also sets `SWAG_AGENTIC_COMMERCE_UCP_PROFILE_FETCHING_DEVELOPMENT_MODE=1` and `MCP_SERVER=1` so http localhost profiles are allowed.

## Stop

```bash
docker compose -f docker/compose.yaml down
```

A recreate of the container decompresses Shopware again and drops plugin files under `/var/www/html`. MySQL (catalog, UCP config) survives the `shopware-mysql` volume. Re-run `./docker/bootstrap.sh` after a recreate.

Add `-v` to drop the MySQL volume (full reinstall on next up).
