"""Resolver de secret_refs opacos → valor real.

Los secrets de proveedores externos (API keys de OpenAI, Grok, Anthropic,
ElevenLabs, etc.) se guardan en la DB SOLO como referencia opaca (`secret_ref`).
El valor en claro vive en el environment del pod (o en un backend tipo
AWS Secrets Manager / Vault). Este módulo expone el lookup transversal.

Convención de `secret_ref`:
  - `env:NOMBRE_DE_LA_VAR` → busca `os.environ['NOMBRE_DE_LA_VAR']`.
  - `vault:path/to/secret` → reservado para integración futura (raise).
  - `aws:arn:aws:secretsmanager:...` → reservado para integración futura (raise).

No se devuelven valores en logs ni en errores: si el secret_ref no se puede
resolver, devolvemos `None` y el caller decide si levanta `ProviderUnavailable`
con un mensaje genérico.
"""
from __future__ import annotations

import os


def resolve_secret_ref(secret_ref: str | None) -> str | None:
    """Resuelve un secret_ref opaco al valor real.

    Args:
        secret_ref: la referencia con prefijo (`env:`, `vault:`, etc.) o
            None / cadena vacía.

    Returns:
        El valor en claro, o None si no se pudo resolver.
    """
    if not secret_ref:
        return None
    ref = secret_ref.strip()
    if not ref:
        return None
    if ref.startswith('env:'):
        env_name = ref[len('env:'):].strip()
        if not env_name:
            return None
        value = os.environ.get(env_name)
        return value if value else None
    # Backends no implementados todavía. Si llega un ref con otro prefijo
    # devolvemos None — el caller (`_require_api_key`) levantará
    # ProviderUnavailable con un mensaje claro.
    return None


def secret_ref_is_configured(secret_ref: str | None) -> bool:
    """True si el secret_ref resuelve a un valor no-vacío."""
    return resolve_secret_ref(secret_ref) is not None


__all__ = ['resolve_secret_ref', 'secret_ref_is_configured']
