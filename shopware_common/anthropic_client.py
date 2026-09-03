# Copyright 2026 shopware AG
# SPDX-License-Identifier: MIT

"""The one place both hosts build their Anthropic client.

The blueprint runtimes (``ShoppingAgent``, ``MerchantAgent``) construct a bare
``AsyncAnthropic`` unless one is passed in. Identity-linked API keys additionally need
the ``anthropic-workspace-id`` header on every request, otherwise the API answers 400
("anthropic-workspace-id is required when authenticating with an identity-linked API
key"). ``ANTHROPIC_WORKSPACE_ID`` supplies that header; when it is unset the client is
exactly what the runtime would have built itself.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from anthropic import NOT_GIVEN, AsyncAnthropic, NotGiven

WORKSPACE_ID_ENV = "ANTHROPIC_WORKSPACE_ID"
WORKSPACE_ID_HEADER = "anthropic-workspace-id"


def workspace_headers(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Headers to attach to every API request: the workspace id when configured,
    nothing otherwise. Surrounding whitespace in the variable is ignored."""
    source = os.environ if environ is None else environ
    workspace_id = (source.get(WORKSPACE_ID_ENV) or "").strip()
    return {WORKSPACE_ID_HEADER: workspace_id} if workspace_id else {}


def build_anthropic_client(
    *, timeout: float | NotGiven = NOT_GIVEN, environ: Mapping[str, str] | None = None
) -> AsyncAnthropic:
    """An ``AsyncAnthropic`` for a runtime's ``client=`` seam. ``timeout`` should be the
    agent config's ``request_timeout_s`` so the client matches the one the runtime would
    otherwise build; credentials still come from the SDK's own chain
    (``ANTHROPIC_API_KEY`` / ``ANTHROPIC_AUTH_TOKEN``)."""
    headers = workspace_headers(environ)
    return AsyncAnthropic(timeout=timeout, default_headers=headers or None)
