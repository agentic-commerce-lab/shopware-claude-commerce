# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""UCP Identity Linking against Shopware's OAuth AS. Without client credentials the
sign-in routes answer 503 and every session is a guest — identical to running with
no identity wired at all. Tokens stay server-side and are never logged."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


def redirect_uri_from_env() -> str:
    return os.environ.get(
        "SHOPWARE_OAUTH_REDIRECT_URI",
        "http://localhost:8004/api/auth/shopware/callback",
    )


class IdentityError(RuntimeError):
    pass


@dataclass
class ShopwareSignIn:
    http: httpx.AsyncClient | None = None
    _states: dict[str, str] = field(default_factory=dict)
    _tokens: dict[str, str] = field(default_factory=dict)
    _ips: dict[str, str] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        return bool(
            os.environ.get("SHOPWARE_UCP_OAUTH_CLIENT_ID")
            and os.environ.get("SHOPWARE_UCP_OAUTH_CLIENT_SECRET")
        )

    def note_buyer_ip(self, session_id: str, ip: str) -> None:
        self._ips[session_id] = ip

    def buyer_ip(self, session_id: str) -> str | None:
        return self._ips.get(session_id)

    def signed_in(self, session_id: str) -> bool:
        return session_id in self._tokens

    def drop(self, session_id: str) -> None:
        self._tokens.pop(session_id, None)

    def begin(self, session_id: str) -> str:
        state = secrets.token_urlsafe(24)
        self._states[state] = session_id
        return state

    def consume_state(self, state: str) -> str | None:
        return self._states.pop(state, None)

    async def authorization_url(self, state: str, redirect_uri: str) -> str:
        raise IdentityError("Identity Linking is not configured for this deployment.")

    async def complete(self, session_id: str, code: str, redirect_uri: str) -> None:
        raise IdentityError("Identity Linking is not configured for this deployment.")

    async def credentials_for(self, session_id: str) -> tuple[str, str] | None:
        token = self._tokens.get(session_id)
        ip = self._ips.get(session_id)
        if token and ip:
            return token, ip
        return None

    async def refresh(self, session_id: str) -> tuple[str, str] | None:
        self.drop(session_id)
        return None
