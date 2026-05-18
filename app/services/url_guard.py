"""Outbound URL validator — single source of truth for SSRF defense.

TASK-0079: any HTTP request whose host/scheme is influenced by tenant input
(webhook alerts, S3 endpoint, WhatsApp media proxy) MUST be validated through
``validate_outbound_url`` before the network call. The validator:

- enforces HTTPS (HTTP only allowed when ``allow_http_for_local_dev=True``
  AND the env says we are in local dev);
- resolves DNS and rejects loopback, RFC1918, link-local, ULA, Google/AWS
  metadata, and explicit ``localhost``/``metadata.*`` hostnames;
- when ``host_allowlist`` is provided, requires a match (wildcard subdomain
  ``*.example.com`` matches ``a.example.com`` and ``example.com``);
- returns the canonical URL string for use; raises ``UnsafeOutboundURLError``
  on any failure.

Bugs covered: BUG01 (webhook alert SSRF), BUG18 (tenant S3 endpoint to local
metadata service with platform creds), BUG19 (WhatsApp media URL escape +
crafted media_id).
"""
from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse, urlunparse

import structlog

log = structlog.get_logger()


class UnsafeOutboundURLError(ValueError):
    """Raised when an outbound URL fails SSRF validation."""


_PRIVATE_NETWORKS: tuple[ipaddress._BaseNetwork, ...] = (
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('169.254.0.0/16'),   # link-local incl. AWS metadata
    ipaddress.ip_network('100.64.0.0/10'),    # carrier-grade NAT
    ipaddress.ip_network('0.0.0.0/8'),         # unspecified
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fc00::/7'),
    ipaddress.ip_network('fe80::/10'),
    # BUG-214 (codex MEDIUM): el original solo bloqueaba `::ffff:127.0.0.0/104`
    # (IPv4-mapped loopback). Pero IPv6 puede expresar TODAS las RFC1918 y
    # link-local ranges via `::ffff:<v4>` — un tenant admin podía configurar
    # webhook URL `https://[::ffff:169.254.169.254]/latest/meta-data/` y
    # bypassear el SSRF guard hacia el AWS metadata service. Agregamos las
    # variantes IPv4-mapped de RFC1918, link-local, CGN y unspecified.
    ipaddress.ip_network('::ffff:127.0.0.0/104'),  # IPv4-mapped loopback
    ipaddress.ip_network('::ffff:10.0.0.0/104'),   # IPv4-mapped RFC1918 class A
    ipaddress.ip_network('::ffff:172.16.0.0/108'), # IPv4-mapped RFC1918 class B
    ipaddress.ip_network('::ffff:192.168.0.0/112'),# IPv4-mapped RFC1918 class C
    ipaddress.ip_network('::ffff:169.254.0.0/112'),# IPv4-mapped link-local
    ipaddress.ip_network('::ffff:100.64.0.0/106'), # IPv4-mapped CGN
    ipaddress.ip_network('::ffff:0.0.0.0/104'),    # IPv4-mapped unspecified
)

_BLOCKED_HOSTNAMES: frozenset[str] = frozenset({
    'localhost',
    'metadata.google.internal',
    'metadata',
    'ip6-localhost',
    'ip6-loopback',
})

# WhatsApp media CDN hosts. Wildcards are permitted via leading ``*.``.
META_MEDIA_HOST_ALLOWLIST: tuple[str, ...] = (
    '*.fbcdn.net',
    '*.cdninstagram.com',
    '*.fbsbx.com',
    'lookaside.fbsbx.com',
    'graph.facebook.com',
    '*.facebook.com',
)

# AWS regional S3 endpoints + virtual-hosted style. MinIO/custom endpoints
# only resolve through this allowlist when the runtime is in local dev mode.
S3_ENDPOINT_HOST_ALLOWLIST: tuple[str, ...] = (
    's3.amazonaws.com',
    '*.s3.amazonaws.com',
    '*.s3.*.amazonaws.com',
    's3.*.amazonaws.com',
    '*.r2.cloudflarestorage.com',
    '*.digitaloceanspaces.com',
)


WhatsAppMediaIdRegex = re.compile(r'^\d{6,30}$')


@dataclass(frozen=True)
class ValidatedURL:
    canonical: str
    host: str
    scheme: str


def _host_matches_allowlist(host: str, allowlist: Iterable[str]) -> bool:
    host_lower = host.lower().rstrip('.')
    for entry in allowlist:
        candidate = entry.lower().rstrip('.')
        if '*' not in candidate:
            if host_lower == candidate:
                return True
            continue
        # Single leading-wildcard ``*.example.com`` matches both the bare
        # suffix (``example.com``) and any deeper subdomain.
        if candidate.startswith('*.') and candidate.count('*') == 1:
            suffix = candidate[2:]  # drop "*."
            if host_lower == suffix or host_lower.endswith('.' + suffix):
                return True
            continue
        # General case (``s3.*.amazonaws.com`` or ``*.s3.*.aws.com``): each
        # ``*`` matches exactly one label.
        regex = '^' + re.escape(candidate).replace(r'\*', r'[^.]+') + '$'
        if re.match(regex, host_lower):
            return True
    return False


def _resolve_addresses(host: str) -> list[ipaddress._BaseAddress]:
    """Return all A/AAAA addresses for ``host``. Empty if DNS fails."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    seen: set[str] = set()
    result: list[ipaddress._BaseAddress] = []
    for info in infos:
        ip_str = info[4][0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        try:
            result.append(ipaddress.ip_address(ip_str))
        except ValueError:
            continue
    return result


def _ip_is_blocked(ip: ipaddress._BaseAddress) -> bool:
    for net in _PRIVATE_NETWORKS:
        if ip in net:
            return True
    # BUG-214 (codex MEDIUM): defense-in-depth — además de las redes
    # `::ffff:*` enumeradas arriba, si el IP es IPv6 con `ipv4_mapped`
    # populated, también lo bloqueamos si el peer v4 cae en una red
    # privada. Cubre casos donde el caller pase la forma `::ffff:<v4>`
    # ya parseada como IPv6Address sin haber expandido a v4 literal.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        v4_peer = ip.ipv4_mapped
        for net in _PRIVATE_NETWORKS:
            if isinstance(net, ipaddress.IPv4Network) and v4_peer in net:
                return True
        if v4_peer.is_unspecified or v4_peer.is_reserved or v4_peer.is_multicast or v4_peer.is_link_local:
            return True
    return ip.is_unspecified or ip.is_reserved or ip.is_multicast


def validate_outbound_url(
    url: str,
    *,
    allowed_schemes: tuple[str, ...] = ('https',),
    host_allowlist: Iterable[str] | None = None,
    allow_http_for_local_dev: bool = False,
    resolver=_resolve_addresses,
) -> ValidatedURL:
    """Validate ``url`` and return its canonical form.

    Args:
        url: full URL provided by tenant or third-party (e.g. Meta Graph).
        allowed_schemes: which schemes are acceptable; by default HTTPS only.
        host_allowlist: optional iterable of literal hosts or ``*.example``
            wildcards; when set, the host must match.
        allow_http_for_local_dev: if True AND env ``APP_ENV in {'local','test'}``
            the validator accepts ``http://`` and skips the private-network
            block. Use only for MinIO/Ollama-style local backends.
        resolver: injectable DNS resolver for tests; defaults to
            ``socket.getaddrinfo``.
    """
    if not isinstance(url, str) or not url.strip():
        raise UnsafeOutboundURLError('url is empty')

    try:
        parsed = urlparse(url.strip())
    except ValueError as exc:
        raise UnsafeOutboundURLError(f'url parse failed: {exc}') from exc

    scheme = (parsed.scheme or '').lower()
    host = (parsed.hostname or '').lower()
    if not scheme or not host:
        raise UnsafeOutboundURLError('url missing scheme or host')

    # Defensive: reject creds embedded in netloc (user:pass@host) — they would
    # be replayed against the validated host and we never want tenants to
    # smuggle credentials through alert webhooks.
    if parsed.username or parsed.password:
        raise UnsafeOutboundURLError('url credentials are not allowed')

    local_dev = allow_http_for_local_dev and _is_local_dev_env()
    schemes = tuple(s.lower() for s in allowed_schemes)
    if scheme not in schemes:
        if scheme == 'http' and local_dev:
            pass
        else:
            raise UnsafeOutboundURLError(f'scheme {scheme!r} not allowed')

    if host in _BLOCKED_HOSTNAMES and not local_dev:
        raise UnsafeOutboundURLError(f'hostname {host!r} is blocked')

    if host_allowlist is not None and not _host_matches_allowlist(host, host_allowlist):
        raise UnsafeOutboundURLError(f'host {host!r} not in allowlist')

    # If the hostname is already an IP literal, validate it directly.
    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if not local_dev and _ip_is_blocked(literal_ip):
            raise UnsafeOutboundURLError(f'ip {literal_ip} is in a blocked network')
        canonical = urlunparse(parsed)
        return ValidatedURL(canonical=canonical, host=host, scheme=scheme)

    # Hostname → resolve and require *all* resolved addresses to be public.
    addresses = resolver(host)
    if not addresses:
        raise UnsafeOutboundURLError(f'host {host!r} did not resolve')

    if not local_dev:
        for ip in addresses:
            if _ip_is_blocked(ip):
                raise UnsafeOutboundURLError(
                    f'host {host!r} resolves to blocked network ({ip})'
                )

    canonical = urlunparse(parsed)
    return ValidatedURL(canonical=canonical, host=host, scheme=scheme)


def _is_local_dev_env() -> bool:
    # Imported lazily so unit tests can monkey-patch settings without import
    # side effects.
    try:
        from app.core.config import get_settings  # noqa: PLC0415

        env = (get_settings().app_env or '').lower()
    except Exception:  # noqa: BLE001
        return False
    return env in {'local', 'test'}


def assert_whatsapp_media_id(media_id: str) -> str:
    """Validate the Meta media_id used to interpolate the Graph URL.

    Meta IDs are numeric strings. Anything else is a crafted payload trying
    to escape the URL path (e.g. ``../foo`` or ``123?token=``).
    """
    if not isinstance(media_id, str):
        raise UnsafeOutboundURLError('media_id must be a string')
    if not WhatsAppMediaIdRegex.match(media_id):
        raise UnsafeOutboundURLError(f'media_id {media_id!r} is not a valid Meta id')
    return media_id


__all__ = (
    'META_MEDIA_HOST_ALLOWLIST',
    'S3_ENDPOINT_HOST_ALLOWLIST',
    'UnsafeOutboundURLError',
    'ValidatedURL',
    'WhatsAppMediaIdRegex',
    'assert_whatsapp_media_id',
    'validate_outbound_url',
)
