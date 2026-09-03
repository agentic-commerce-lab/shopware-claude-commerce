# Copyright 2026 shopware AG
# SPDX-License-Identifier: MIT

"""UCP Identity Linking against Shopware's OAuth authorization server.

Shopware's ``SwagAgenticCommerce`` implements ``dev.ucp.shopping.identity_linking`` as a
**platform-to-shop** OAuth 2.0 Authorization Code + PKCE (S256) flow
(``/.well-known/oauth-authorization-server``):

* ``client_id`` is the platform profile URI (``UCP-Agent`` profile) and **must be HTTPS**;
  the authorize request must be RFC 9421-signed with a key from that profile.
* ``GET /ucp/v1/oauth/authorize`` needs the *customer's* Store API context token in
  ``sw-context-token`` — a logged-in Shopware customer, which this host obtains through
  ``POST /store-api/account/login``. The authorization code comes back in the JSON body
  (``code``, ``redirect_to``); there is no browser hop.
* ``POST /ucp/v1/oauth/token`` (``token_endpoint_auth_methods_supported: ["none"]``)
  exchanges code + ``code_verifier`` for ``access_token`` / ``refresh_token``; scopes
  ``dev.ucp.shopping.cart:manage`` and ``dev.ucp.shopping.order:read``.

Without a signer or with an ``http://`` profile (the local Docker lane publishes
``http://localhost/agent-profile.json``) the flow cannot pass Shopware's client binding;
:attr:`ShopwareIdentityLinking.unavailable_reason` says so and the sign-in routes answer
503. Guest mode is unaffected. Tokens and passwords stay in memory and are never logged.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .store_api import StoreApiClient, StoreApiError
from .ucp_client import UcpClient

logger = logging.getLogger(__name__)

SCOPES = ("dev.ucp.shopping.cart:manage", "dev.ucp.shopping.order:read")
CLIENT_ID_ENV = "SHOPWARE_UCP_OAUTH_CLIENT_ID"
REDIRECT_URI_ENV = "SHOPWARE_OAUTH_REDIRECT_URI"
DEFAULT_REDIRECT_PATH = "/api/auth/shopware/callback"
AUTHORIZE_PATH = "/ucp/v1/oauth/authorize"
TOKEN_PATH = "/ucp/v1/oauth/token"
CONTEXT_TOKEN_HEADER = "sw-context-token"
_EXPIRY_MARGIN_SECONDS = 30
_DEFAULT_EXPIRES_IN = 3600
_TIMEOUT = httpx.Timeout(20.0)


class IdentityError(RuntimeError):
    pass


class IdentityUnavailable(IdentityError):
    """The deployment cannot run identity linking (no signer / non-HTTPS profile)."""


@dataclass
class LinkedIdentity:
    access_token: str
    refresh_token: str | None
    expires_at: float
    scope: str
    customer_context_token: str
    subject: str | None = None

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at - _EXPIRY_MARGIN_SECONDS


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class ShopwareIdentityLinking:
    def __init__(
        self,
        client: UcpClient,
        store_api: StoreApiClient,
        *,
        public_url: str,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client
        self._store_api = store_api
        self._http = http or httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False)
        self.client_id = os.environ.get(CLIENT_ID_ENV) or client.profile_url
        self.redirect_uri = (
            os.environ.get(REDIRECT_URI_ENV) or f"{public_url.rstrip('/')}{DEFAULT_REDIRECT_PATH}"
        )
        self._linked: dict[str, LinkedIdentity] = {}

    # ------------------------------------------------------------------ availability

    @property
    def unavailable_reason(self) -> str | None:
        if self._client.signer is None:
            return (
                "Identity Linking needs a signing key (UCP_AGENT_SIGNING_KEY_PEM_FILE): "
                "Shopware only accepts signed authorize requests."
            )
        if urlparse(self.client_id).scheme != "https":
            return (
                "Identity Linking needs an HTTPS platform profile as client_id "
                f"(current profile: {self.client_id}); Shopware refuses http:// profiles. "
                "Guest mode still works."
            )
        return None

    @property
    def configured(self) -> bool:
        return self.unavailable_reason is None

    # ------------------------------------------------------------------ state per session

    def signed_in(self, session_id: str) -> bool:
        return session_id in self._linked

    def identity(self, session_id: str) -> LinkedIdentity | None:
        return self._linked.get(session_id)

    def drop(self, session_id: str) -> None:
        self._linked.pop(session_id, None)

    async def bearer(self, session_id: str) -> str | None:
        """The session's access token, refreshed when it is about to expire."""
        linked = self._linked.get(session_id)
        if linked is None:
            return None
        if linked.expired:
            linked = await self.refresh(session_id)
            if linked is None:
                return None
        return linked.access_token

    # ------------------------------------------------------------------ the flow

    async def link(self, session_id: str, email: str, password: str) -> LinkedIdentity:
        reason = self.unavailable_reason
        if reason:
            raise IdentityUnavailable(reason)
        try:
            customer_token = await self._store_api.login(email, password)
        except StoreApiError as error:
            if error.status in {401, 403}:
                raise IdentityError("Shopware rejected the customer credentials") from error
            raise IdentityError(f"Shopware login failed ({error.status})") from error
        verifier, challenge = _pkce_pair()
        state = secrets.token_urlsafe(24)
        code = await self._authorize(customer_token, state, challenge)
        tokens = await self._token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "code_verifier": verifier,
            }
        )
        linked = LinkedIdentity(
            access_token=str(tokens["access_token"]),
            refresh_token=tokens.get("refresh_token"),
            expires_at=time.time() + float(tokens.get("expires_in") or _DEFAULT_EXPIRES_IN),
            scope=str(tokens.get("scope") or " ".join(SCOPES)),
            customer_context_token=customer_token,
        )
        self._linked[session_id] = linked
        logger.info("identity linked for session %s (scope %s)", session_id, linked.scope)
        return linked

    async def refresh(self, session_id: str) -> LinkedIdentity | None:
        linked = self._linked.get(session_id)
        if linked is None or not linked.refresh_token:
            self.drop(session_id)
            return None
        try:
            tokens = await self._token(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": linked.refresh_token,
                    "client_id": self.client_id,
                }
            )
        except IdentityError as error:
            logger.info("identity refresh failed for session %s: %s", session_id, error)
            self.drop(session_id)
            return None
        linked.access_token = str(tokens["access_token"])
        linked.refresh_token = tokens.get("refresh_token") or linked.refresh_token
        linked.expires_at = time.time() + float(tokens.get("expires_in") or _DEFAULT_EXPIRES_IN)
        return linked

    async def _authorize(self, customer_token: str, state: str, challenge: str) -> str:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "scope": " ".join(SCOPES),
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        url = f"{self._client.shop_url}{AUTHORIZE_PATH}?{query}"
        headers = {
            "Accept": "application/json",
            "UCP-Agent": self._client.agent_header,
            CONTEXT_TOKEN_HEADER: customer_token,
        }
        assert self._client.signer is not None
        headers.update(self._client.signer.headers_for("GET", url, b""))
        try:
            response = await self._http.get(url, headers=headers)
        except httpx.HTTPError as error:
            raise IdentityError(f"authorize request failed: {error}") from error
        code = _code_from_authorize(response, state)
        if code is None:
            raise IdentityError(
                f"authorize refused ({response.status_code}): {_error_text(response)}"
            )
        return code

    async def _token(self, form: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._client.shop_url}{TOKEN_PATH}"
        body = httpx.Request("POST", url, json=form).content
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "UCP-Agent": self._client.agent_header,
        }
        if self._client.signer is not None:
            headers.update(self._client.signer.headers_for("POST", url, body))
        try:
            response = await self._http.post(url, content=body, headers=headers)
        except httpx.HTTPError as error:
            raise IdentityError(f"token request failed: {error}") from error
        if response.status_code >= 400:
            raise IdentityError(
                f"token endpoint refused ({response.status_code}): {_error_text(response)}"
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise IdentityError("token endpoint returned no JSON") from error
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise IdentityError("token endpoint returned no access_token")
        return payload


def _code_from_authorize(response: httpx.Response, state: str) -> str | None:
    location = response.headers.get("location")
    if response.status_code in {302, 303} and location:
        return _code_from_redirect(location, state)
    if response.status_code >= 400:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("state") not in {None, state}:
        return None
    if payload.get("code"):
        return str(payload["code"])
    redirect_to = payload.get("redirect_to")
    if isinstance(redirect_to, str):
        return _code_from_redirect(redirect_to, state)
    return None


def _code_from_redirect(url: str, state: str) -> str | None:
    params = parse_qs(urlparse(url).query)
    if params.get("state", [state])[0] != state:
        return None
    codes = params.get("code") or []
    return codes[0] if codes else None


def _error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(payload, dict):
        messages = payload.get("messages")
        if isinstance(messages, list) and messages:
            first = messages[0] if isinstance(messages[0], dict) else {}
            return str(first.get("content") or first)
        return str(
            payload.get("error_description")
            or payload.get("error")
            or payload.get("detail")
            or payload
        )[:200]
    return str(payload)[:200]
