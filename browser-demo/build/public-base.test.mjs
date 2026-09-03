// Copyright 2026 shopware AG
// SPDX-License-Identifier: MIT

import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  injectPublicBaseBanner,
  prefixManifestUrls,
  publicBasePrefix,
  rewriteEngineSource,
  viteBaseFromEnv,
} from './public-base.mjs';

describe('public base (GitHub Pages project path)', () => {
  it('normalises DEMO_BASE_PATH for Vite', () => {
    assert.equal(viteBaseFromEnv({}), '/');
    assert.equal(viteBaseFromEnv({ DEMO_BASE_PATH: '/' }), '/');
    assert.equal(viteBaseFromEnv({ DEMO_BASE_PATH: '' }), '/');
    assert.equal(viteBaseFromEnv({ DEMO_BASE_PATH: '/shopware_claude_commerce' }), '/shopware_claude_commerce/');
    assert.equal(viteBaseFromEnv({ DEMO_BASE_PATH: '/shopware_claude_commerce/' }), '/shopware_claude_commerce/');
    assert.equal(viteBaseFromEnv({ DEMO_BASE_PATH: 'shopware_claude_commerce' }), '/shopware_claude_commerce/');
  });

  it('uses an empty worker prefix at the origin root', () => {
    assert.equal(publicBasePrefix('/'), '');
    assert.equal(publicBasePrefix('/shopware_claude_commerce/'), '/shopware_claude_commerce');
  });

  it('rewrites quoted engine paths once and leaves already-prefixed paths alone', () => {
    const source = `import { Lite4MariaDB } from '/mariadb/index.mjs'; fetch('/php/auto_prepend.php'); fetch("/versions/6.7.13.1/shopware.zip");`;
    const prefix = '/shopware_claude_commerce';
    const once = rewriteEngineSource(source, prefix);
    assert.match(once, /from '\/shopware_claude_commerce\/mariadb\/index\.mjs'/);
    assert.match(once, /fetch\('\/shopware_claude_commerce\/php\/auto_prepend\.php'\)/);
    assert.match(once, /fetch\("\/shopware_claude_commerce\/versions\/6\.7\.13\.1\/shopware\.zip"\)/);
    assert.equal(rewriteEngineSource(once, prefix), once);
    assert.equal(rewriteEngineSource(source, ''), source);
  });

  it('injects a rewritable __DEMO_PUBLIC_BASE__ banner', () => {
    const first = injectPublicBaseBanner('console.log(1);\n', '/shopware_claude_commerce');
    assert.equal(first, 'self.__DEMO_PUBLIC_BASE__ = "/shopware_claude_commerce";\nconsole.log(1);\n');
    const second = injectPublicBaseBanner(first, '');
    assert.equal(second, 'self.__DEMO_PUBLIC_BASE__ = "";\nconsole.log(1);\n');
  });

  it('prefixes versions.json zip and dump URLs', () => {
    const manifest = {
      default: '6.7.13.1',
      versions: [{ id: '6.7.13.1', zip: '/versions/6.7.13.1/shopware.zip', dump: '/versions/6.7.13.1/shopware.sql.gz' }],
    };
    const prefixed = prefixManifestUrls(manifest, '/shopware_claude_commerce');
    assert.equal(prefixed.versions[0].zip, '/shopware_claude_commerce/versions/6.7.13.1/shopware.zip');
    assert.equal(prefixManifestUrls(prefixed, '/shopware_claude_commerce').versions[0].zip, prefixed.versions[0].zip);
    assert.equal(prefixManifestUrls(manifest, '').versions[0].zip, '/versions/6.7.13.1/shopware.zip');
  });
});
