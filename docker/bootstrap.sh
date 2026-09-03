#!/usr/bin/env bash
# Bootstrap Shopware in docker: wait until healthy, install SwagAgenticCommerce,
# expose UCP on the Storefront sales channel, seed catalog extras, write credentials.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/docker/compose.yaml")
CONTAINER="${SHOPWARE_CONTAINER:-commerce-agents-shopware}"
SHOP_URL="${SHOPWARE_PUBLIC_URL:-http://localhost:8080}"
ADMIN_USER="${SHOPWARE_ADMIN_USERNAME:-admin}"
ADMIN_PASS="${SHOPWARE_ADMIN_PASSWORD:-shopware}"
PLUGIN_REPO="${SWAG_AGENTIC_COMMERCE_REPO:-https://github.com/shopware/agentic-commerce.git}"
SDK_REPO="${UCP_PHP_SDK_REPO:-https://github.com/agentic-commerce-alliance/ucp-php-sdk.git}"
MERCHANT_TOOLS_REPO="${SWAG_MCP_MERCHANT_TOOLS_REPO:-https://github.com/shopware/SwagMcpMerchantTools.git}"

exec_shop() {
  docker exec -u www-data "$CONTAINER" bash -lc "cd /var/www/html && $*"
}

exec_root() {
  docker exec -u root "$CONTAINER" bash -lc "$*"
}

wait_for_shop() {
  echo "Waiting for Shopware Admin API at ${SHOP_URL} ..."
  local i code
  for i in $(seq 1 90); do
    # `/` is 400 until sales_channel_domain matches the published port. Admin API
    # 401 (no token) means PHP + Shopware are up.
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "${SHOP_URL}/api/_info/version" || true)"
    if [[ "${code}" == "401" || "${code}" == "200" ]]; then
      echo "Shopware is answering HTTP (${code})."
      return 0
    fi
    sleep 4
  done
  echo "Shopware did not become ready in time. docker logs ${CONTAINER}:" >&2
  docker logs --tail 80 "$CONTAINER" >&2 || true
  return 1
}

wait_for_mysql() {
  echo "Waiting for MySQL inside ${CONTAINER} ..."
  local i
  for i in $(seq 1 60); do
    if docker exec -u root "$CONTAINER" bash -lc "mysqladmin -uroot -proot ping --silent" >/dev/null 2>&1; then
      echo "MySQL is up."
      return 0
    fi
    sleep 2
  done
  echo "MySQL did not become ready in time." >&2
  return 1
}

mysql_shop() {
  docker exec -u root "$CONTAINER" bash -lc "mysql -uroot -proot shopware -N -e \"$1\""
}

echo "==> Starting compose stack"
"${COMPOSE[@]}" up -d

wait_for_shop
wait_for_mysql

echo "==> Shopware version"
exec_shop 'php bin/console --version || true'
exec_shop 'php bin/console system:config:get core.app.shopName || true'

echo "==> Point sales-channel domains at ${SHOP_URL}"
# Dockware defaults to http://localhost (port 80). We publish 8080:80.
exec_root "mysql -uroot -proot shopware -e \"UPDATE sales_channel_domain SET url='${SHOP_URL}' WHERE url LIKE 'http://localhost%' OR url LIKE 'https://localhost%';\""
exec_root "if grep -q '^APP_URL=' /var/www/html/.env; then sed -i 's|^APP_URL=.*|APP_URL=${SHOP_URL}|' /var/www/html/.env; else echo 'APP_URL=${SHOP_URL}' >> /var/www/html/.env; fi"
exec_shop 'php bin/console cache:clear --no-warmup || true'

echo "==> Enable MCP_SERVER feature flag when present (6.7.11–13)"
exec_root "grep -q '^MCP_SERVER=' /var/www/html/.env || echo 'MCP_SERVER=1' >> /var/www/html/.env"
# UCP SDK blocks http://localhost profile fetches unless this is on (local Docker only).
exec_root "grep -q '^SWAG_AGENTIC_COMMERCE_UCP_PROFILE_FETCHING_DEVELOPMENT_MODE=' /var/www/html/.env || echo 'SWAG_AGENTIC_COMMERCE_UCP_PROFILE_FETCHING_DEVELOPMENT_MODE=1' >> /var/www/html/.env"
exec_shop 'php bin/console feature:dump >/tmp/features.json 2>/dev/null || true'
exec_shop 'php bin/console cache:clear --no-warmup || true'

PLUGIN_DIR="/var/www/html/custom/plugins/SwagAgenticCommerce"
echo "==> Install SwagAgenticCommerce"
if ! exec_root "test -f ${PLUGIN_DIR}/composer.json"; then
  exec_root "git clone --depth 1 '${PLUGIN_REPO}' ${PLUGIN_DIR}"
else
  echo "Plugin already present."
fi
exec_root "chown -R www-data:www-data /var/www/html/custom/plugins"

install_sdk() {
  if exec_shop 'composer show ucp-php-sdk/symfony-bundle >/dev/null 2>&1'; then
    echo "ucp-php-sdk already installed."
    return 0
  fi
  echo "Requiring ucp-php-sdk/symfony-bundle from Packagist..."
  if exec_shop 'COMPOSER_MEMORY_LIMIT=-1 composer require ucp-php-sdk/symfony-bundle:">=0.0.5 <0.1.0" --no-interaction --no-scripts'; then
    return 0
  fi
  echo "Packagist require failed; cloning SDK as path repositories."
  exec_root "git clone --depth 1 '${SDK_REPO}' /var/www/html/custom/ucp-php-sdk"
  exec_shop 'composer config repositories.ucp-sdk-core "{\"type\":\"path\",\"url\":\"custom/ucp-php-sdk/packages/core\",\"options\":{\"symlink\":true,\"versions\":{\"ucp-php-sdk/core\":\"0.0.5\"}}}"'
  exec_shop 'composer config repositories.ucp-sdk-symfony "{\"type\":\"path\",\"url\":\"custom/ucp-php-sdk/packages/symfony-bundle\",\"options\":{\"symlink\":true,\"versions\":{\"ucp-php-sdk/symfony-bundle\":\"0.0.5\"}}}"'
  exec_shop 'COMPOSER_MEMORY_LIMIT=-1 composer require ucp-php-sdk/symfony-bundle:0.0.5 --no-interaction --no-scripts'
}

if ! install_sdk; then
  echo "WARNING: could not install ucp-php-sdk. UCP plugin may fail; Store API fallback remains." >&2
fi

exec_shop 'php bin/console plugin:refresh'
if exec_shop 'php bin/console plugin:list --json' | grep -q 'SwagAgenticCommerce'; then
  exec_shop 'php bin/console plugin:install --activate SwagAgenticCommerce --reinstall || php bin/console plugin:install --activate SwagAgenticCommerce || php bin/console plugin:activate SwagAgenticCommerce'
  exec_shop 'php bin/console cache:clear'
else
  echo "WARNING: SwagAgenticCommerce not listed after plugin:refresh." >&2
fi

echo "==> Optional SwagMcpMerchantTools"
MERCHANT_DIR="/var/www/html/custom/plugins/SwagMcpMerchantTools"
if ! exec_root "test -f ${MERCHANT_DIR}/composer.json"; then
  exec_root "git clone --depth 1 '${MERCHANT_TOOLS_REPO}' ${MERCHANT_DIR} || true"
fi
exec_root "chown -R www-data:www-data /var/www/html/custom/plugins"
exec_shop 'php bin/console plugin:refresh || true'
exec_shop 'php bin/console plugin:install --activate SwagMcpMerchantTools || true'

echo "==> Install CommerceAgentsHandoff (adopts UCP cart token into the storefront session)"
HANDOFF_SRC="$ROOT/docker/plugins/CommerceAgentsHandoff"
HANDOFF_DIR="/var/www/html/custom/plugins/CommerceAgentsHandoff"
if [[ -f "${HANDOFF_SRC}/composer.json" ]]; then
  docker cp "${HANDOFF_SRC}/." "${CONTAINER}:${HANDOFF_DIR}"
  exec_root "chown -R www-data:www-data ${HANDOFF_DIR}"
  exec_shop 'php bin/console plugin:refresh || true'
  exec_shop 'php bin/console plugin:install --activate CommerceAgentsHandoff || php bin/console plugin:activate CommerceAgentsHandoff || true'
  exec_shop 'php bin/console cache:clear --no-warmup || true'
fi

echo "==> Expose UCP on the Storefront sales channel"
python3 "$ROOT/docker/enable_ucp.py" --shop-url "$SHOP_URL" --container "$CONTAINER"

echo "==> Seed extra catalog (variants, OOS, Grundpreis)"
python3 "$ROOT/docker/seed_catalog.py" --shop-url "$SHOP_URL" --user "$ADMIN_USER" --password "$ADMIN_PASS"
exec_shop 'php bin/console dal:refresh:index --no-interaction || true'

echo "==> Write docker/.generated.env"
python3 "$ROOT/docker/write_credentials.py" --shop-url "$SHOP_URL" --container "$CONTAINER" --out "$ROOT/docker/.generated.env"

echo "==> Publish agent-profile.json into the shop (reachable as http://localhost/agent-profile.json from inside the container)"
docker cp "$ROOT/agent-profile.json" "${CONTAINER}:/var/www/html/public/agent-profile.json"
exec_root "chown www-data:www-data /var/www/html/public/agent-profile.json"
exec_root "mysql -uroot -proot shopware -e \"DELETE FROM ucp_platform_profile_cache; DELETE FROM ucp_negotiation_sessions;\" || true"

echo "==> Verify UCP discovery"
if curl -fsS "${SHOP_URL}/.well-known/ucp" | head -c 400; then
  echo
  echo "UCP discovery OK."
else
  echo
  echo "WARNING: /.well-known/ucp did not return a profile. Store API fallback still works." >&2
fi

echo "Bootstrap finished."
echo "  Storefront  ${SHOP_URL}"
echo "  Admin       ${SHOP_URL}/admin  (${ADMIN_USER} / ${ADMIN_PASS})"
echo "  Credentials ${ROOT}/docker/.generated.env"
