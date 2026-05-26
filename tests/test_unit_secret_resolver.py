"""Cobertura completa de `app.services.secret_resolver`."""
from __future__ import annotations

from app.services.secret_resolver import (
    resolve_secret_ref,
    secret_ref_is_configured,
)


class TestResolveSecretRef:
    def test_none_returns_none(self):
        assert resolve_secret_ref(None) is None

    def test_empty_string_returns_none(self):
        assert resolve_secret_ref('') is None

    def test_whitespace_only_returns_none(self):
        assert resolve_secret_ref('   ') is None

    def test_env_prefix_with_set_var(self, monkeypatch):
        monkeypatch.setenv('FOO_KEY', 'super-secret')
        assert resolve_secret_ref('env:FOO_KEY') == 'super-secret'

    def test_env_prefix_with_unset_var_returns_none(self, monkeypatch):
        monkeypatch.delenv('NOT_SET_AT_ALL', raising=False)
        assert resolve_secret_ref('env:NOT_SET_AT_ALL') is None

    def test_env_prefix_with_empty_var_returns_none(self, monkeypatch):
        monkeypatch.setenv('EMPTY_VAR', '')
        assert resolve_secret_ref('env:EMPTY_VAR') is None

    def test_env_prefix_with_no_var_name_returns_none(self):
        assert resolve_secret_ref('env:') is None
        assert resolve_secret_ref('env:   ') is None

    def test_unknown_prefix_returns_none(self):
        # `vault:` y `aws:` no implementados todavía — devuelven None.
        assert resolve_secret_ref('vault:path/to/secret') is None
        assert resolve_secret_ref('aws:arn:aws:secretsmanager:...') is None

    def test_no_prefix_returns_none(self):
        # Sin prefijo conocido, no resolvemos.
        assert resolve_secret_ref('some-raw-string') is None

    def test_strips_whitespace_around_ref(self, monkeypatch):
        monkeypatch.setenv('STRIPPED_KEY', 'value-x')
        assert resolve_secret_ref('  env:STRIPPED_KEY  ') == 'value-x'


class TestSecretRefIsConfigured:
    def test_true_when_env_var_set(self, monkeypatch):
        monkeypatch.setenv('PRESENT', 'x')
        assert secret_ref_is_configured('env:PRESENT') is True

    def test_false_when_unresolved(self):
        assert secret_ref_is_configured(None) is False
        assert secret_ref_is_configured('') is False
        assert secret_ref_is_configured('vault:x') is False

    def test_false_when_env_var_empty(self, monkeypatch):
        monkeypatch.setenv('EMPTY', '')
        assert secret_ref_is_configured('env:EMPTY') is False
