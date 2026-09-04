// Copyright 2026 shopware AG
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { after, before, describe, it } from 'node:test';

const APP_ROUTE = new URL('../playground/src/app-route.mjs', import.meta.url);
const playgroundPresent = existsSync(APP_ROUTE);

describe('app-route classification under a project Pages prefix', { skip: playgroundPresent ? false : 'playground not fetched' }, async () => {
  if (!playgroundPresent) return;

  const { isEngineBypassPath, isShopwarePhpPath, isStaticPlaygroundPath, postToWindowClient } = await import(APP_ROUTE.href);
  const previous = globalThis.self;

  before(() => {
    globalThis.self = { __DEMO_PUBLIC_BASE__: '/shopware_claude_commerce' };
  });

  after(() => {
    if (previous === undefined) delete globalThis.self;
    else globalThis.self = previous;
  });

  it('never routes demo host artifacts or PHP prelude files to PHP WASM', () => {
    const staticPaths = [
      '/shopware_claude_commerce/demo/host/bootstrap.py',
      '/shopware_claude_commerce/demo/host/repo-tree.tar',
      '/shopware_claude_commerce/php/auto_prepend.php',
      '/shopware_claude_commerce/demo/wheels/manifest.json',
    ];
    for (const path of staticPaths) {
      assert.equal(isEngineBypassPath(path), true, path);
      assert.equal(isStaticPlaygroundPath(path), true, path);
      assert.equal(isShopwarePhpPath(path, false), false, path);
    }
  });

  it('still treats the storefront front controller as PHP', () => {
    assert.equal(isShopwarePhpPath('/shopware_claude_commerce/index.php', true), true);
    assert.equal(isEngineBypassPath('/shopware_claude_commerce/index.php'), false);
  });

  it('posts PHP bridge messages with transfer options, then the legacy list', () => {
    const calls = [];
    const client = {
      postMessage(_message, second) {
        calls.push(second);
        if (second && typeof second === 'object' && !Array.isArray(second)) {
          throw new Error('options form unsupported');
        }
      },
    };
    postToWindowClient(client, { type: 'php-request' }, ['port']);
    assert.deepEqual(calls[0], { transfer: ['port'] });
    assert.deepEqual(calls[1], ['port']);
  });
});
