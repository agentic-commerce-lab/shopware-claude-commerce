#!/usr/bin/env python3
"""Dump Shopware credentials for the storefront/merchant hosts into docker/.generated.env."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def mysql(container: str, sql: str) -> str:
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
    lines = [
        line.strip()
        for line in (result.stdout or "").splitlines()
        if line.strip() and not line.startswith("mysql:")
    ]
    return lines[-1] if lines else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shop-url", required=True)
    parser.add_argument("--container", default="commerce-agents-shopware")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    row = mysql(
        args.container,
        "SELECT LOWER(HEX(sc.id)), sc.access_key "
        "FROM sales_channel sc "
        "JOIN sales_channel_domain scd ON scd.sales_channel_id = sc.id "
        "WHERE sc.type_id = UNHEX('8a243080f92e4c719546314b577cf82b') "
        "LIMIT 1;",
    )
    sales_channel_id = ""
    access_key = ""
    if row:
        parts = row.split()
        sales_channel_id = parts[0]
        access_key = parts[1] if len(parts) > 1 else ""

    lines = [
        f"SHOPWARE_URL={args.shop_url.rstrip('/')}",
        f"SHOPWARE_ADMIN_URL={args.shop_url.rstrip('/')}",
        f"SHOPWARE_SALES_CHANNEL_ID={sales_channel_id}",
        f"SHOPWARE_SALES_CHANNEL_ACCESS_KEY={access_key}",
        f"UCP_AGENT_PROFILE_URL=http://localhost/agent-profile.json",
        "UCP_TRANSPORT=rest",
        "SHOPWARE_ADMIN_USERNAME=admin",
        "SHOPWARE_ADMIN_PASSWORD=shopware",
        "SHOPWARE_ADMIN_TRANSPORT=rest",
    ]
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
