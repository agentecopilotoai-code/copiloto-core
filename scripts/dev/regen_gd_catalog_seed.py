#!/usr/bin/env python3
"""Regenera el bloque de seed (catálogo de roles + permisos + matriz)
dentro de ``infra/postgres/modules/gd.sql`` a partir de las constantes
canónicas en ``app.gd.bootstrap``.

Razón de tener este script: las constantes canónicas viven en Python
(`_GD_SYSTEM_ROLES`, `_GD_PERMISOS_CATALOGO`, `_GD_MATRIZ_ROL_MODULO`)
porque el `bootstrap_gd_for_tenant` las consume al activar el módulo via
PATCH. Pero el SQL de inicialización (`modules/gd.sql`) también debe
seedearlas porque `bootstrap.sh --reset --yes --module=gd` activa
Demo Taller directamente vía SQL, sin pasar por el PATCH → sin el seed
SQL, el catálogo queda vacío → todos los endpoints gateados con
`require_gd_permission(...)` devuelven 403.

Uso (desde dentro del container `api`, donde está disponible `app.gd.bootstrap`)::

    docker compose exec -T api python /app/scripts/dev/regen_gd_catalog_seed.py

El script modifica ``infra/postgres/modules/gd.sql`` in-place.

Idempotente: el bloque generado usa ON CONFLICT DO NOTHING, así que
re-correr el bootstrap.sh sobre una DB que ya tenía catálogo no
duplica filas.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Cuando se ejecuta dentro del container, el repo está montado en /app.
# Asumimos que app/ está en el sys.path (lo agregamos defensivo).
sys.path.insert(0, '/app')

from app.gd.bootstrap import (  # noqa: E402
    _GD_MATRIZ_ROL_MODULO,
    _GD_PERMISOS_CATALOGO,
    _GD_SYSTEM_ROLES,
    _USO_TO_ALCANCE,
)


def q(s: str) -> str:
    """Escape de comilla simple SQL."""
    return s.replace("'", "''")


def generate_sql() -> str:
    lines: list[str] = []
    out = lines.append

    out('-- =============================================================================')
    out('-- Catálogo de roles, permisos y matriz rol×permiso')
    out('-- =============================================================================')
    out('-- Fuente: app.gd.bootstrap (_GD_SYSTEM_ROLES, _GD_PERMISOS_CATALOGO,')
    out('-- _GD_MATRIZ_ROL_MODULO). Generado por scripts/dev/regen_gd_catalog_seed.py.')
    out('--')
    out('-- IMPORTANTE: si modificás los catálogos en bootstrap.py, regenerá este')
    out('-- bloque para mantener consistencia entre carga via SQL (bootstrap.sh)')
    out('-- y carga via PATCH (UI).')
    out('--')
    out('-- Idempotente: ON CONFLICT DO NOTHING.')
    out('-- =============================================================================')
    out('')

    # 1. Roles del sistema
    out(f'-- ── {len(_GD_SYSTEM_ROLES)} roles del sistema GD ──')
    out('insert into gd.rol (codigo, nombre, descripcion, es_sistema, estado) values')
    rows = [
        f"  ('{q(codigo)}', '{q(nombre)}', '{q(desc)}', true, 'activo')"
        for codigo, nombre, desc in _GD_SYSTEM_ROLES
    ]
    out(',\n'.join(rows))
    out('on conflict (codigo) do nothing;')
    out('')

    # 2. Permisos del catálogo
    out(f'-- ── {len(_GD_PERMISOS_CATALOGO)} permisos del catálogo GD ──')
    out('insert into gd.permiso (codigo, nombre, modulo, es_critico, estado) values')
    rows = [
        f"  ('{q(codigo)}', '{q(nombre)}', '{q(modulo)}', "
        f"{'true' if critico else 'false'}, 'activo')"
        for codigo, modulo, nombre, critico in _GD_PERMISOS_CATALOGO
    ]
    out(',\n'.join(rows))
    out('on conflict (codigo) do nothing;')
    out('')

    # 3. Matriz rol×permiso (~582 filas)
    matriz_rows: list[str] = []
    permisos_por_modulo: dict[str, list[str]] = {}
    for codigo, modulo, _, _ in _GD_PERMISOS_CATALOGO:
        permisos_por_modulo.setdefault(modulo, []).append(codigo)

    for rol_codigo, mod_uso in _GD_MATRIZ_ROL_MODULO.items():
        for modulo, uso in mod_uso.items():
            alcance = _USO_TO_ALCANCE.get(uso)
            if alcance is None:
                continue
            for permiso in permisos_por_modulo.get(modulo, []):
                matriz_rows.append(
                    f"  ('{q(rol_codigo)}', '{q(permiso)}', "
                    f"'{q(alcance)}', 'activo')"
                )

    out(f'-- ── {len(matriz_rows)} filas de matriz rol×permiso ──')
    out('insert into gd.rol_permiso (rol_codigo, permiso_codigo, alcance_default, estado) values')
    out(',\n'.join(matriz_rows))
    out('on conflict (rol_codigo, permiso_codigo) do nothing;')

    return '\n'.join(lines)


def main() -> int:
    sql_file = Path('/app/infra/postgres/modules/gd.sql')
    if not sql_file.exists():
        print(f'ERROR: no se encontró {sql_file}', file=sys.stderr)
        return 1

    contenido = sql_file.read_text(encoding='utf-8')
    nuevo_seed = generate_sql()

    # Reemplazar bloque existente si está, o insertar antes del marker.
    bloque_pattern = re.compile(
        r'-- =+\n'
        r'-- Catálogo de roles, permisos y matriz rol×permiso\n'
        r'-- =+\n'
        r'.*?'
        r'on conflict \(rol_codigo, permiso_codigo\) do nothing;\n',
        re.DOTALL,
    )
    if bloque_pattern.search(contenido):
        nuevo_contenido = bloque_pattern.sub(nuevo_seed + '\n', contenido)
        print('→ bloque existente reemplazado')
    else:
        marker = (
            '-- ============================================================================\n'
            '-- Activación automática del módulo para Demo Taller (dev local)'
        )
        if marker not in contenido:
            print(
                'ERROR: no encontré el marker de activación Demo Taller. '
                'El archivo gd.sql cambió de estructura.',
                file=sys.stderr,
            )
            return 2
        nuevo_contenido = contenido.replace(marker, nuevo_seed + '\n\n' + marker)
        print('→ bloque insertado antes de la activación Demo Taller')

    sql_file.write_text(nuevo_contenido, encoding='utf-8')
    print(f'✓ {sql_file} actualizado.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
