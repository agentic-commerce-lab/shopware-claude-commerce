#!/usr/bin/env python3
"""Enable UCP on the Storefront sales channel inside the running Shopware container."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

UCP_VERSION = "2026-04-08"


def run(container: str, sql: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-u",
            "root",
            "-e",
            "MYSQL_PWD=root",
            container,
            "bash",
            "-lc",
            f"mysql -uroot -s -N shopware -e {json.dumps(sql)}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "mysql failed")
    return result.stdout.strip()


def exec_console(container: str, args: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-u",
            "www-data",
            container,
            "bash",
            "-lc",
            f"cd /var/www/html && php bin/console {args}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return (result.stdout or "") + (result.stderr or "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shop-url", required=True)
    parser.add_argument("--container", default="commerce-agents-shopware")
    args = parser.parse_args()

    exists = run(
        args.container,
        "SHOW TABLES LIKE 'swag_agentic_commerce_ucp_config';",
    )
    if not exists:
        print("UCP config table missing — plugin did not install. Skipping UCP exposure.", file=sys.stderr)
        return 0

    row = run(
        args.container,
        "SELECT CONCAT(LOWER(HEX(sc.id)), ' ', sc.access_key) "
        "FROM sales_channel sc "
        "JOIN sales_channel_domain scd ON scd.sales_channel_id = sc.id "
        "WHERE sc.type_id = UNHEX('8a243080f92e4c719546314b577cf82b') "
        "ORDER BY scd.url DESC LIMIT 1;",
    )
    if not row:
        print("No storefront sales channel found.", file=sys.stderr)
        return 1
    sales_channel_id, access_key = row.split(" ", 1)
    print(f"Storefront sales channel {sales_channel_id}")

    config = {
        "active": True,
        "ucpVersion": UCP_VERSION,
        "profileDomain": args.shop_url.rstrip("/"),
        "enabledCapabilities": [
            "catalog",
            "cart",
            "discount",
            "checkout",
            "order",
            "identity_linking",
        ],
        "enabledTransports": ["rest", "mcp", "embedded"],
        "continueUrlTemplate": args.shop_url.rstrip("/")
        + "/checkout/confirm?checkoutId={checkoutId}",
        "platformAllowlist": ["localhost", "127.0.0.1"],
        "remoteProfileAllowlist": ["localhost", "127.0.0.1"],
        "agentAllowlist": ["localhost", "127.0.0.1"],
        "embeddedAllowedOrigins": [
            "http://localhost:3005",
            "http://127.0.0.1:3005",
            "http://localhost:8004",
            "http://127.0.0.1:8004",
        ],
        "embeddedFrameAncestors": [
            "http://localhost:3005",
            "http://127.0.0.1:3005",
        ],
        "discoveryBudget": 10,
        "catalogResultLimit": 50,
        "webhookUrlOverride": None,
        "signaturePolicy": "log",
        "idempotencyRequired": True,
    }
    payload = json.dumps(config).replace("'", "\\'")
    sql = (
        "INSERT INTO swag_agentic_commerce_ucp_config "
        "(sales_channel_id, config_json, created_at, updated_at) VALUES "
        f"(UNHEX('{sales_channel_id}'), '{payload}', NOW(3), NOW(3)) "
        "ON DUPLICATE KEY UPDATE config_json=VALUES(config_json), updated_at=NOW(3);"
    )
    run(args.container, sql)

    show = exec_console(args.container, f"ucp:config:show --sales-channel={sales_channel_id} --no-interaction")
    print(show[-2000:])
    set_out = exec_console(
        args.container,
        "ucp:config:set --no-interaction "
        f"--sales-channel={sales_channel_id} "
        "--signature-policy=log --idempotency=true "
        f"--continue-url-template={args.shop_url.rstrip('/')}/checkout/confirm?checkoutId={{checkoutId}} "
        "--embedded-allowed-origins=http://localhost:3005 "
        "--embedded-frame-ancestors=http://localhost:3005 "
        "--agent-allowlist=localhost --agent-allowlist=127.0.0.1 "
        "--remote-profile-allowlist=localhost --remote-profile-allowlist=127.0.0.1 "
        "--platform-allowlist=localhost --platform-allowlist=127.0.0.1",
    )
    print(set_out[-1500:])
    keys = exec_console(
        args.container,
        f"ucp:signing-keys:generate --sales-channel={sales_channel_id} --no-interaction || true",
    )
    print(keys[-800:])
    exec_console(args.container, "cache:clear --no-warmup || true")
    print(f"UCP enabled. Store API access key prefix: {access_key[:8]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
