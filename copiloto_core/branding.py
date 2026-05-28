"""BrandingConfig — marca propia del deployment.

Cada cliente que arma su SaaS sobre el core (ej. SAT Guajira) tiene
su propia identidad visual. El admin del core respeta esa marca via
`branding` config y exponiendo un endpoint `GET /v1/branding` que el
SPA del módulo lee al cargar para ajustar logo + colores + nombre.

# Uso

```python
from copiloto_core import create_app, BrandingConfig

app = create_app(
    branding=BrandingConfig(
        product_name="SAT Monitoreo & Alertas",
        logo_url="/static/sat-logo.svg",
        primary_color="#0F1E33",
        accent_color="#22d3ee",
        support_email="soporte@satguajira.com",
        copyright_holder="SAT Guajira S.A.S.",
    ),
)
```

El endpoint `GET /v1/branding` (público, sin auth) devuelve estos
valores como JSON. El SPA propio del módulo lo fetcha al cargar para
inyectar tokens CSS / strings i18n / etc.

# Defaults

Si no pasás `branding`, el deployment se brandea como "CopilotoIA"
genérico. Útil para dev/staging sin cliente identificado.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass


# Regex hex color con 3 o 6 dígitos, con `#` opcional pero recomendado.
_HEX_COLOR_RE = re.compile(r'^#?[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$')


@dataclass(frozen=True)
class BrandingConfig:
    """Identidad visual del deployment.

    Args:
      product_name: nombre del producto que el cliente final ve.
        Aparece en `<title>`, headers, emails transaccionales.
      logo_url: URL del logo. Puede ser absoluta (CDN) o relativa
        (servida por uno de los `static_mounts` del módulo).
      primary_color: hex color principal (con o sin `#`). Usado en
        sidebar, botones primary, accents.
      accent_color: hex color secundario (highlights, links activos).
      support_email: dónde el usuario reporta problemas. Footer + 401/403
        error pages.
      copyright_holder: nombre legal del cliente. Footer del SPA +
        emails.
      privacy_url: URL de la política de privacidad (links footer).
      terms_url: URL de los términos de servicio.

    Raises:
      ValueError: si product_name está vacío, o los colores no son hex.
    """

    product_name: str = 'CopilotoIA'
    logo_url: str | None = None
    primary_color: str = '#0F1E33'
    accent_color: str = '#22d3ee'
    support_email: str | None = None
    copyright_holder: str = 'CopilotoIA'
    privacy_url: str | None = None
    terms_url: str | None = None

    def __post_init__(self) -> None:
        if not self.product_name or not isinstance(self.product_name, str):
            raise ValueError('BrandingConfig.product_name requerido (str no vacío)')
        for field_name in ('primary_color', 'accent_color'):
            val = getattr(self, field_name)
            if not isinstance(val, str) or not _HEX_COLOR_RE.match(val):
                raise ValueError(
                    f'BrandingConfig.{field_name} debe ser hex color '
                    f'(ej. "#0F1E33"), got {val!r}',
                )
        # Normalizar colores: SIEMPRE con `#` y lowercase.
        # Como es frozen, usamos object.__setattr__.
        for field_name in ('primary_color', 'accent_color'):
            v = getattr(self, field_name).lower()
            if not v.startswith('#'):
                v = '#' + v
            object.__setattr__(self, field_name, v)

    def to_public_dict(self) -> dict:
        """Diccionario serializable para `GET /v1/branding`.

        Útil para SPA del módulo que necesita marca en runtime.
        Incluye TODOS los campos (incluyendo `None` cuando no setteado)
        para que el frontend tenga el shape consistente.
        """
        return asdict(self)


__all__ = ['BrandingConfig']
