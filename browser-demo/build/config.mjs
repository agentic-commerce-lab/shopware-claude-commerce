// Copyright 2026 shopware AG
// SPDX-License-Identifier: MIT

/**
 * Single source of truth for every pin and path the build pipeline uses.
 * Override any pin through the environment variable named next to it.
 */
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const DEMO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
export const REPO_ROOT = resolve(DEMO_ROOT, '..');

/** FriendsOfShopware/shopware-playground: PHP WASM + MariaDB WASM engine, Shopware 6.7.13.1 tree. */
export const PLAYGROUND_REPO =
  process.env.PLAYGROUND_REPO || 'https://github.com/FriendsOfShopware/shopware-playground.git';
export const PLAYGROUND_COMMIT =
  process.env.PLAYGROUND_COMMIT || 'c86f241a628734dd066ddec5c545e03e904bec2b';
export const PLAYGROUND_DIR = process.env.PLAYGROUND_DIR
  ? resolve(process.env.PLAYGROUND_DIR)
  : join(DEMO_ROOT, 'playground');
export const SHOP_DIR = join(PLAYGROUND_DIR, 'shopware');
export const PLAYGROUND_PUBLIC = join(PLAYGROUND_DIR, 'public');

/** Same pins as docker/bootstrap.sh (docs/version-matrix.md). */
export const SWAG_AGENTIC_COMMERCE_REPO =
  process.env.SWAG_AGENTIC_COMMERCE_REPO || 'https://github.com/shopware/agentic-commerce.git';
export const SWAG_AGENTIC_COMMERCE_REF =
  process.env.SWAG_AGENTIC_COMMERCE_REF || '20bd3df360c6c6622eed8e20fa5db66b8a6e1a86';
export const SWAG_AGENTIC_COMMERCE_VERSION = '1.3.0';
export const UCP_SDK_CONSTRAINT = '>=0.0.5 <0.1.0';

/** Plugins copied from this repository into the WASM shop (read-only sources). */
export const REPO_PLUGINS = [
  { name: 'CommerceAgentsHandoff', source: join(REPO_ROOT, 'docker/plugins/CommerceAgentsHandoff'), composer: 'commerce-agents/handoff' },
  { name: 'SwagCommerceAgentTools', source: join(REPO_ROOT, 'shopware-plugins/SwagCommerceAgentTools'), composer: 'swag/commerce-agent-tools' },
  { name: 'DemoOverlay', source: join(DEMO_ROOT, 'plugins/DemoOverlay'), composer: 'commerce-agents/demo-overlay' },
];

/** Playground admin user (src/admin-credentials.mjs in the playground). */
export const ADMIN_USERNAME = 'admin';
export const ADMIN_PASSWORD = 'Shopware123!';

/** Loopback HTTP shim that fronts PHP WASM while the repo's Python seed scripts run. */
export const SEED_HTTP_PORT = Number(process.env.SEED_HTTP_PORT || 4180);
export const SEED_ORIGIN = `http://127.0.0.1:${SEED_HTTP_PORT}`;

/**
 * The UCP platform profile URI the shop is told about. The shop never fetches it (no
 * outbound HTTP from WASM): the profile is pre-seeded into `ucp_platform_profile_cache`
 * with `expires_at = NULL`. A fixed loopback URI keeps the cache row valid for any origin
 * the demo is served from; the SDK's development mode accepts plain http for it.
 */
export const AGENT_PROFILE_URL = 'http://127.0.0.1/agent-profile.json';
export const UCP_SIGNATURE_POLICY = process.env.UCP_SIGNATURE_POLICY || 'strict';

/** Pyodide (CPython 3.14) distribution the agent host runs on. */
export const PYODIDE_VERSION = process.env.PYODIDE_VERSION || '314.0.6';
export const PYODIDE_CDN = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
/** Pyodide-built packages (compiled or pinned by the distribution) the host loads. */
export const PYODIDE_PACKAGES = [
  'micropip',
  'pydantic',
  'jiter',
  'httpx',
  'httpcore',
  'anyio',
  'cryptography',
  'sqlalchemy',
  'pyyaml',
  'jsonschema',
  'fastapi',
  'starlette',
  'distro',
  'certifi',
  'idna',
  'h11',
  'sniffio',
  'attrs',
  'referencing',
  'rpds-py',
  'jsonschema_specifications',
  'typing-extensions',
  'annotated-types',
  'typing-inspection',
  'pycparser',
  'cffi',
  'six',
  'packaging',
  'annotated-doc',
];

/** Pure-Python wheels pinned to requirements.txt (built by build/build-wheels.sh). */
export const BLUEPRINT_COMMIT = 'fd4d59224ab96b43c6dc6888207c67b3bd5a24cf';

export const DIST_DIR = join(DEMO_ROOT, 'dist');
export const SITE_DIR = join(DIST_DIR, 'site');
export const APP_DIR = join(DEMO_ROOT, 'app');
export const HOST_DIR = join(DEMO_ROOT, 'host');
/** Everything under app/public/demo is served at /demo/* (bypassed by the playground SW). */
export const APP_PUBLIC_DEMO = join(APP_DIR, 'public', 'demo');

export const DEV_PORT = Number(process.env.PORT || 4188);
