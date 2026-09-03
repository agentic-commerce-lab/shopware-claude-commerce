# Copyright 2026 shopware AG
# SPDX-License-Identifier: MIT

from anthropic import AsyncAnthropic

from shopware_common.anthropic_client import (
    WORKSPACE_ID_ENV,
    WORKSPACE_ID_HEADER,
    build_anthropic_client,
    workspace_headers,
)

BASE_ENV = {"ANTHROPIC_API_KEY": "sk-ant-test"}
WORKSPACE_ID = "wrkspc_01TESTWORKSPACE"


def test_no_workspace_header_without_the_variable(monkeypatch):
    monkeypatch.delenv(WORKSPACE_ID_ENV, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert workspace_headers() == {}
    client = build_anthropic_client()
    assert isinstance(client, AsyncAnthropic)
    assert WORKSPACE_ID_HEADER not in client.default_headers


def test_blank_variable_counts_as_unset():
    environ = {**BASE_ENV, WORKSPACE_ID_ENV: "   "}
    assert workspace_headers(environ) == {}
    assert WORKSPACE_ID_HEADER not in build_anthropic_client(environ=environ).default_headers


def test_workspace_header_is_sent_when_configured():
    environ = {**BASE_ENV, WORKSPACE_ID_ENV: f" {WORKSPACE_ID}\n"}
    assert workspace_headers(environ) == {WORKSPACE_ID_HEADER: WORKSPACE_ID}
    client = build_anthropic_client(environ=environ)
    assert client.default_headers[WORKSPACE_ID_HEADER] == WORKSPACE_ID


def test_timeout_matches_the_runtime_config():
    client = build_anthropic_client(timeout=42.0, environ=BASE_ENV)
    assert client.timeout == 42.0
