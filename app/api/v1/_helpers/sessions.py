"""Auth session constants extracted from app/api/v1/routes.py."""
from __future__ import annotations


# BUG-168: ventana de actividad para considerar una sesión "viva". Si la
# pestaña no ha hecho hit al endpoint en este tiempo, asumimos que su JWT
# expiró (typical JWT TTL es 8h-24h) o que el navegador se cerró. El
# default de 24h cubre el caso común (sesión laboral o ciclo nocturno).
AUTH_SESSION_ACTIVE_HOURS = 24
