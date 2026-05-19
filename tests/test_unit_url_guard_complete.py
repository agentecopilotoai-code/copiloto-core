"""Completeness tests for url_guard — covers DNS failure, invalid IP parse,
IPv4-mapped IPv6 private ranges (BUG-214), and the get_settings exception path
inside _is_local_dev_env.
"""
from __future__ import annotations

import ipaddress
import socket

import pytest

from app.services import url_guard as guard


# ── Lines 131-132: DNS resolver gaierror returns [] ─────────────────────────


def test_resolve_addresses_returns_empty_on_gaierror(monkeypatch):
    def boom(*_a, **_kw):
        raise socket.gaierror('nope')

    monkeypatch.setattr(guard.socket, 'getaddrinfo', boom)
    assert guard._resolve_addresses('nx.example') == []


def test_validate_raises_when_resolver_returns_empty():
    with pytest.raises(guard.UnsafeOutboundURLError, match='did not resolve'):
        guard.validate_outbound_url('https://nx.example/', resolver=lambda h: [])


# ── Lines 142-143: ip_address() ValueError in _resolve_addresses ────────────


def test_resolve_addresses_skips_unparseable_ip(monkeypatch):
    class FakeInfo:
        def __init__(self, ip):
            self._ip = ip

        def __getitem__(self, idx):
            assert idx == 4
            return (self._ip, 0)

    def fake_getaddrinfo(host, port):
        # First entry parseable, second entry junk (covers continue branch),
        # third entry is duplicate of first (covers seen-dedup branch).
        return [
            ('inet', None, None, '', ('93.184.216.34', 0)),
            ('inet', None, None, '', ('not-an-ip', 0)),
            ('inet', None, None, '', ('93.184.216.34', 0)),
        ]

    monkeypatch.setattr(guard.socket, 'getaddrinfo', fake_getaddrinfo)
    result = guard._resolve_addresses('example.com')
    assert len(result) == 1
    assert str(result[0]) == '93.184.216.34'


# ── Lines 157-162: IPv4-mapped IPv6 → private v4 peer blocked ──────────────


def test_ipv4_mapped_loopback_blocked():
    ip = ipaddress.ip_address('::ffff:127.0.0.1')
    assert guard._ip_is_blocked(ip)


def test_ipv4_mapped_rfc1918_blocked():
    # 10.0.0.5 mapped — should hit the v4_peer loop and match RFC1918
    ip = ipaddress.ip_address('::ffff:10.0.0.5')
    assert guard._ip_is_blocked(ip)


def test_ipv4_mapped_link_local_blocked():
    # 169.254.169.254 (AWS metadata) mapped
    ip = ipaddress.ip_address('::ffff:169.254.169.254')
    assert guard._ip_is_blocked(ip)


def test_ipv4_mapped_multicast_via_v4_peer_check():
    # 224.0.0.1 multicast — covered by `v4_peer.is_multicast` branch
    ip = ipaddress.ip_address('::ffff:224.0.0.1')
    assert guard._ip_is_blocked(ip)


def test_ipv4_mapped_public_v4_not_blocked():
    ip = ipaddress.ip_address('::ffff:93.184.216.34')
    # public mapped → ipv4_mapped is not None but no private/specials apply
    assert guard._ip_is_blocked(ip) is False


def test_validate_blocks_url_with_ipv4_mapped_metadata_literal():
    # End-to-end: literal IPv6 in URL pointing at AWS metadata via v4-mapped
    with pytest.raises(guard.UnsafeOutboundURLError, match='blocked'):
        guard.validate_outbound_url(
            'https://[::ffff:169.254.169.254]/latest/meta-data/',
            resolver=lambda h: [ipaddress.ip_address('93.184.216.34')],
        )


# ── Lines 255-256: _is_local_dev_env handles get_settings exception ─────────


def test_is_local_dev_env_returns_false_when_get_settings_raises(monkeypatch):
    import app.services.url_guard as mod

    def boom():
        raise RuntimeError('settings unavailable')

    # Monkeypatch the import target — function does `from app.core.config import get_settings`
    import app.core.config as cfg
    monkeypatch.setattr(cfg, 'get_settings', boom)
    assert mod._is_local_dev_env() is False


def test_is_local_dev_env_returns_true_for_local(monkeypatch):
    import app.core.config as cfg

    class FakeSettings:
        app_env = 'local'

    monkeypatch.setattr(cfg, 'get_settings', lambda: FakeSettings())
    assert guard._is_local_dev_env() is True


def test_is_local_dev_env_returns_false_for_prod(monkeypatch):
    import app.core.config as cfg

    class FakeSettings:
        app_env = 'production'

    monkeypatch.setattr(cfg, 'get_settings', lambda: FakeSettings())
    assert guard._is_local_dev_env() is False


# ── Line 110: literal (non-wildcard) allowlist match ────────────────────────


def test_host_allowlist_literal_match():
    # 'graph.facebook.com' is a literal entry in META_MEDIA_HOST_ALLOWLIST
    result = guard.validate_outbound_url(
        'https://graph.facebook.com/v18.0/me',
        host_allowlist=guard.META_MEDIA_HOST_ALLOWLIST,
        resolver=lambda h: [ipaddress.ip_address('157.240.10.10')],
    )
    assert result.host == 'graph.facebook.com'


# ── Line 160: defense-in-depth — v4_peer matches IPv4Network via mapped ────


def test_ipv4_mapped_via_v4_peer_network_loop(monkeypatch):
    """The outer loop covers all IPv4 ranges via ::ffff:*/N mappings, so the
    defensive v4_peer-in-IPv4Network branch (line 159-160) is reached only if
    the IPv4-mapped networks are removed from PRIVATE_NETWORKS. Simulate that
    to exercise the defense-in-depth path."""
    only_v4_nets = tuple(
        n for n in guard._PRIVATE_NETWORKS if isinstance(n, ipaddress.IPv4Network)
    )
    monkeypatch.setattr(guard, '_PRIVATE_NETWORKS', only_v4_nets)
    ip = ipaddress.ip_address('::ffff:192.168.0.1')
    assert guard._ip_is_blocked(ip) is True
