#!/usr/bin/env node
// Copyright 2026 shopware AG
// SPDX-License-Identifier: MIT

/**
 * GitHub Actions: PHP WASM migrations trap on hosted runners; local prepare-shop
 * produces the seed dump. Copy the tracked ci-fixtures into the playground bundle
 * so prepare-shop.mjs skips the in-WASM installer (dump + install.lock + shop-config).
 *
 * Regenerate after bootstrap changes:
 *   FORCE_INSTALL=1 node build/prepare-shop.mjs
 *   cp playground/public/versions/<v>/shopware.sql.gz ci-fixtures/<v>/
 *   cp app/public/demo/shop-config.json ci-fixtures/<v>/
 */
import { cpSync, existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { pathToFileURL } from 'node:url';
import { APP_PUBLIC_DEMO, DEMO_ROOT, PLAYGROUND_DIR, PLAYGROUND_PUBLIC, SHOP_DIR } from './config.mjs';
import { log } from './lib.mjs';

const { detectShopwareVersion } = await import(
  pathToFileURL(join(PLAYGROUND_DIR, 'src/shopware-version.mjs')).href,
);

if (process.env.GITHUB_ACTIONS !== 'true') {
  process.exit(0);
}

const version = detectShopwareVersion(SHOP_DIR);
if (!version) throw new Error('cannot detect Shopware version for CI fixtures');

const fixtureDir = join(DEMO_ROOT, 'ci-fixtures', version);
const dumpSrc = join(fixtureDir, 'shopware.sql.gz');
const configSrc = join(fixtureDir, 'shop-config.json');
if (!existsSync(dumpSrc) || !existsSync(configSrc)) {
  throw new Error(`CI fixtures missing for ${version} in ${fixtureDir}`);
}

const versionDir = join(PLAYGROUND_PUBLIC, 'versions', version);
mkdirSync(versionDir, { recursive: true });
cpSync(dumpSrc, join(versionDir, 'shopware.sql.gz'));
mkdirSync(APP_PUBLIC_DEMO, { recursive: true });
cpSync(configSrc, join(APP_PUBLIC_DEMO, 'shop-config.json'));
writeFileSync(join(SHOP_DIR, 'install.lock'), `ci-fixture ${new Date().toISOString()}\n`);
log(`CI fixtures seeded for Shopware ${version} (prepare-shop will skip WASM install)`);
