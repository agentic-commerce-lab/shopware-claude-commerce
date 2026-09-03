// Copyright 2026 shopware AG
// SPDX-License-Identifier: MIT

import { useState } from 'react';
import type { AnthropicAccess } from '../../../host/protocol';
import type { DemoState } from '../engine/demo';

type Props = {
  state: DemoState;
  onClose: () => void;
  onSave: (access: Partial<AnthropicAccess>) => void;
};

/**
 * Model access. Proxy: the local Node server (browser-demo/server) holds the Anthropic key,
 * forwards /api/anthropic/* and enforces per-session budgets. BYOK: the visitor's own key, sent
 * straight to api.anthropic.com from the agent-host worker with
 * `anthropic-dangerous-direct-browser-access`; it lives in memory only.
 */
export default function KeyDialog({ state, onClose, onSave }: Props) {
  const [mode, setMode] = useState<AnthropicAccess['mode']>(state.anthropic.mode);
  const [apiKey, setApiKey] = useState(state.anthropic.apiKey || '');
  const [workspaceId, setWorkspaceId] = useState(state.anthropic.workspaceId || '');
  const proxyReady = state.proxyStatus === 'ready';
  const canSave = mode === 'proxy' ? proxyReady : apiKey.trim().startsWith('sk-ant-');
  const proxyHint =
    state.proxyStatus === 'ready'
      ? 'The local server adds the demo key server-side, streams the answer back and enforces a per-tab budget.'
      : state.proxyStatus === 'unconfigured'
        ? 'The local server is running without ANTHROPIC_API_KEY. Add it to the repo .env and restart, or use your own key.'
        : state.proxyStatus === 'absent'
          ? 'Not available on this host (static deployment). Use your own key.'
          : 'Checking the local server…';

  return (
    <div className="demo-dialog__backdrop" onClick={onClose} role="presentation">
      <div className="demo-dialog" role="dialog" aria-modal="true" aria-labelledby="demo-key-title" onClick={(event) => event.stopPropagation()} data-testid="key-dialog">
        <h2 id="demo-key-title">How should Claude be called?</h2>
        <p>Everything else already runs in this tab. Only the Messages API call leaves the browser.</p>

        <label className="demo-choice" data-active={mode === 'proxy'} data-disabled={!proxyReady}>
          <input type="radio" name="mode" checked={mode === 'proxy'} disabled={!proxyReady} onChange={() => setMode('proxy')} />
          <span>
            <strong>Local demo proxy{proxyReady ? ' (default)' : ''}</strong>
            <span data-testid="proxy-hint">{proxyHint}</span>
          </span>
        </label>

        <label className="demo-choice" data-active={mode === 'byok'}>
          <input type="radio" name="mode" checked={mode === 'byok'} onChange={() => setMode('byok')} />
          <span>
            <strong>Bring your own key</strong>
            <span>
              Sent directly to api.anthropic.com with <code>anthropic-dangerous-direct-browser-access</code>. Kept in this tab's memory only —
              never stored, never sent anywhere else.
            </span>
            {mode === 'byok' ? (
              <>
                <label htmlFor="demo-api-key">Anthropic API key</label>
                <input
                  id="demo-api-key"
                  type="password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder="sk-ant-…"
                  autoComplete="off"
                  spellCheck={false}
                  data-testid="byok-key"
                />
                <label htmlFor="demo-workspace-id">Workspace id (identity-linked keys only)</label>
                <input id="demo-workspace-id" value={workspaceId} onChange={(event) => setWorkspaceId(event.target.value)} placeholder="wrkspc_…" spellCheck={false} />
              </>
            ) : null}
          </span>
        </label>

        <div className="demo-dialog__actions">
          <button type="button" className="demo-pill" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="demo-pill demo-pill--accent"
            disabled={!canSave}
            data-testid="key-save"
            onClick={() => {
              onSave(mode === 'proxy' ? { mode, apiKey: '', workspaceId: '' } : { mode, apiKey: apiKey.trim(), workspaceId: workspaceId.trim() });
              onClose();
            }}
          >
            Use this
          </button>
        </div>
      </div>
    </div>
  );
}
