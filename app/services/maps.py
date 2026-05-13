"""Google Maps URL builder for tenant locations and branches.

Used by ``app.api.v1.routes`` when a branch is created or updated without an
explicit ``maps_url``. Avoids the geocoding API by trusting the admin-provided
coordinates / address.
"""
from __future__ import annotations

from urllib.parse import quote

MAPS_BASE_URL = 'https://www.google.com/maps/search/?api=1&query='


def build_maps_url(
    lat: float | None = None,
    lng: float | None = None,
    address: str | None = None,
) -> str | None:
    """Return a canonical Google Maps search URL or ``None``.

    Priority:
    1. ``lat,lng`` when both are present and valid floats in range.
    2. URL-encoded ``address`` otherwise.
    3. ``None`` if neither is usable.
    """
    if lat is not None and lng is not None:
        try:
            lat_f = float(lat)
            lng_f = float(lng)
        except (TypeError, ValueError):
            lat_f = None
            lng_f = None
        if (
            lat_f is not None
            and lng_f is not None
            and -90.0 <= lat_f <= 90.0
            and -180.0 <= lng_f <= 180.0
        ):
            return f'{MAPS_BASE_URL}{quote(f"{lat_f},{lng_f}", safe=",")}'

    if address:
        trimmed = address.strip()
        if trimmed:
            return f'{MAPS_BASE_URL}{quote(trimmed, safe="")}'

    return None
