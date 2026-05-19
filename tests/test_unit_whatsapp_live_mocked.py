"""HTTPx-mocked tests for `app/services/whatsapp.py` live-mode paths.

Stubs `httpx.AsyncClient` with a fake that captures requests and returns
canned responses, so we exercise the template + media + send paths
without touching the real Meta Graph API.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest


# ───────── Fake httpx ──────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int = 200, json_body: Any = None, text: str = ''):
        self.status_code = status_code
        self._json = json_body if json_body is not None else {}
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            req = httpx.Request('POST', 'https://x')
            raise httpx.HTTPStatusError('error', request=req, response=self)


class _FakeAsyncClient:
    """Records requests; returns canned responses in order."""
    def __init__(self, *args, **kwargs):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def post(self, url, *args, **kwargs):
        self.calls.append(('POST', url, kwargs))
        return self._respond()

    async def get(self, url, *args, **kwargs):
        self.calls.append(('GET', url, kwargs))
        return self._respond()

    async def delete(self, url, *args, **kwargs):
        self.calls.append(('DELETE', url, kwargs))
        return self._respond()

    def _respond(self):
        return _FakeResponse(200, json_body={'id': 'msg_1', 'data': [{'name': 't1'}]})


def _patch_httpx_with_token(monkeypatch, secret_dir, **fake_responses):
    """Pre-write a valid Meta token secret + patch httpx.AsyncClient."""
    from app.services import whatsapp as wa
    monkeypatch.setattr(wa, '_candidate_secret_paths', lambda name: [secret_dir / name])
    monkeypatch.setattr(wa.httpx, 'AsyncClient', _FakeAsyncClient)


# ───────── send_whatsapp_message live path ───────────────────────────────


def test_send_whatsapp_message_live_calls_meta(monkeypatch, tmp_path):
    secret_dir = tmp_path / '.secrets'
    secret_dir.mkdir()
    (secret_dir / 'wa_token').write_text('EAAGm0PX4ZCpsBO_real_meta_token')

    from app.services import whatsapp as wa
    monkeypatch.setattr(wa, '_candidate_secret_paths', lambda name: [secret_dir / name])
    monkeypatch.setattr(wa.httpx, 'AsyncClient', _FakeAsyncClient)

    async def _go():
        return await wa.send_whatsapp_message(
            phone_number_id='pn-1',
            to='5730099887766',
            message_type='text',
            text='Hola',
            delivery_mode='live',
            token_ref='secrets/wa_token',
        )

    out = asyncio.run(_go())
    # Returns the mocked JSON body
    assert isinstance(out, dict)


# ───────── submit_template_to_meta httpx-mocked ──────────────────────────


def test_submit_template_to_meta_success(monkeypatch, tmp_path):
    secret_dir = tmp_path / '.secrets'
    secret_dir.mkdir()
    (secret_dir / 'wa_token').write_text('EAAGm0PX4ZCpsBO_real_meta_token')

    from app.services import whatsapp as wa
    monkeypatch.setattr(wa, '_candidate_secret_paths', lambda name: [secret_dir / name])
    monkeypatch.setattr(wa.httpx, 'AsyncClient', _FakeAsyncClient)

    async def _go():
        return await wa.submit_template_to_meta(
            waba_id='waba-1', token_ref='secrets/wa_token',
            name='hello_world', locale='es', category='utility',
            components={'body': {'text': 'Hola'}},
        )

    out = asyncio.run(_go())
    assert isinstance(out, dict)


def test_fetch_templates_from_meta_returns_list(monkeypatch, tmp_path):
    secret_dir = tmp_path / '.secrets'
    secret_dir.mkdir()
    (secret_dir / 'wa_token').write_text('EAAGm0PX4ZCpsBO_real_meta_token')

    from app.services import whatsapp as wa
    monkeypatch.setattr(wa, '_candidate_secret_paths', lambda name: [secret_dir / name])
    monkeypatch.setattr(wa.httpx, 'AsyncClient', _FakeAsyncClient)

    async def _go():
        return await wa.fetch_templates_from_meta(
            waba_id='waba-1', token_ref='secrets/wa_token',
        )

    out = asyncio.run(_go())
    assert isinstance(out, list)
    assert out and out[0]['name'] == 't1'


def test_fetch_templates_from_meta_handles_non_list_body(monkeypatch, tmp_path):
    """If Meta returns a body without a `data` array, the helper returns []."""
    secret_dir = tmp_path / '.secrets'
    secret_dir.mkdir()
    (secret_dir / 'wa_token').write_text('EAAGm0PX4ZCpsBO_real_meta_token')

    class _NoDataClient(_FakeAsyncClient):
        def _respond(self):
            return _FakeResponse(200, json_body={'unexpected': 'shape'})

    from app.services import whatsapp as wa
    monkeypatch.setattr(wa, '_candidate_secret_paths', lambda name: [secret_dir / name])
    monkeypatch.setattr(wa.httpx, 'AsyncClient', _NoDataClient)

    async def _go():
        return await wa.fetch_templates_from_meta(
            waba_id='waba-1', token_ref='secrets/wa_token',
        )

    assert asyncio.run(_go()) == []


def test_delete_template_from_meta_success(monkeypatch, tmp_path):
    secret_dir = tmp_path / '.secrets'
    secret_dir.mkdir()
    (secret_dir / 'wa_token').write_text('EAAGm0PX4ZCpsBO_real_meta_token')

    from app.services import whatsapp as wa
    monkeypatch.setattr(wa, '_candidate_secret_paths', lambda name: [secret_dir / name])
    monkeypatch.setattr(wa.httpx, 'AsyncClient', _FakeAsyncClient)

    async def _go():
        await wa.delete_template_from_meta(
            waba_id='waba-1', token_ref='secrets/wa_token',
            template_name='t1',
        )

    # Returns None (no raise = success)
    assert asyncio.run(_go()) is None
