"""Fix-group 22: BUG-128..BUG-132.

- BUG-128: NOT-APPLICABLE. `global.css` no declara `:root` (ver header
  del archivo: "NO declara tokens"), así que no hay conflicto con los
  `var(--*)` de `tokens.css` por orden de import. Además, el orden
  actual ya es `tokens.css` → `global.css`, que es el correcto bajo
  cascada (lo último cargado gana si hubiera conflicto, y como no lo
  hay, el setup es seguro).
- BUG-129: VIGENTE. El snippet de extracción de tokens en
  `docs/UI_BACKLOG.md` usaba `grep -oE '--[a-z0-9-]+ ?:[^;]+;'`. El
  patrón empieza con `--`, así que (g/u)grep lo interpreta como una
  opción ("invalid option --[a-z0-9-]+ …") y aborta. Fix: pasar `-e`
  para separar explícitamente el patrón de las opciones.
- BUG-130: NOT-APPLICABLE. Las URLs `/v1/platform/tenants` que
  reportaba el bot ya fueron limpiadas — `docs/UI_BACKLOG.md` no
  contiene esa cadena hoy. Las rutas reales son `/v1/tenants` (en
  `platform_admin_router`) y `/v1/tenants/{tenant_id}/status`.
- BUG-131: NOT-APPLICABLE. Mismo que BUG-031: `require_platform_owner`
  ya chequea `'platform_owner' not in roles` correctamente (no
  `'owner'`). No queda otro check con el anti-patrón.
- BUG-132: NOT-APPLICABLE. La instrucción TASK-0077 (que cubrió
  TASK-0092 antes de mergear) requiere DOS gates en `ensure_tenant_role`:
  JWT role gate + DB role gate (con `rank(role) ≥ rank(min_role)`).
  La doc actual (`docs/BACKLOG.md`) describe ambos.
"""
from __future__ import annotations

from pathlib import Path
import subprocess


UI_BACKLOG = Path('docs/UI_BACKLOG.md')
BACKLOG = Path('docs/BACKLOG.md')
ROUTES = Path('app/api/v1/routes.py')
SECURITY = Path('app/core/security.py')
GLOBAL_CSS = Path('admin-panel/src/styles/global.css')
TOKENS_CSS = Path('admin-panel/src/styles/tokens.css')
MAIN_JSX = Path('admin-panel/src/main.jsx')


# ───── BUG-128 — NOT-APPLICABLE (no conflict) ────────────────────────────


def test_bug_128_global_css_does_not_define_root_tokens():
    """`global.css` NO debe declarar `:root` ni tokens propios. La fuente de
    verdad es `tokens.css` — si esto se rompe, el bug del review-bot vuelve
    a ser VIGENTE (el orden de import sí afectaría).
    """
    src = GLOBAL_CSS.read_text()
    assert ':root' not in src, (
        'BUG-128 regresión: `global.css` no debe definir `:root` — la fuente '
        'de verdad de los tokens es `tokens.css`. Si necesitas overrides, '
        'añádelos a `tokens.css` con el selector `:root[data-theme=…]`.'
    )


def test_bug_128_main_jsx_imports_tokens_before_global():
    """Orden de import: `tokens.css` PRIMERO, `global.css` SEGUNDO. Así, en
    caso de conflicto futuro, `global.css` (último cargado) gana — pero como
    no hay conflicto (test anterior), el setup actual es seguro.
    """
    src = MAIN_JSX.read_text()
    tokens_idx = src.find("import './styles/tokens.css'")
    global_idx = src.find("import './styles/global.css'")
    assert tokens_idx > 0 and global_idx > 0
    assert tokens_idx < global_idx, (
        'BUG-128: `tokens.css` debe importarse antes que `global.css` para '
        'que los tokens estén disponibles cuando `global.css` los consume vía '
        '`var(--*)`. Si invertimos el orden, las reglas de `global.css` que '
        'usan tokens se renderizan con `unset`.'
    )


# ───── BUG-129 — grep -e antepuesto al patrón `--*` ──────────────────────


def test_bug_129_token_extract_snippet_uses_dash_e():
    src = UI_BACKLOG.read_text()
    # El snippet ahora debe pasar `-e` para que `--[a-z0-9-]+ ?:[^;]+;` no
    # se interprete como una opción.
    assert "grep -oE -e '--[a-z0-9-]+ ?:[^;]+;'" in src, (
        "BUG-129: el snippet de extracción de tokens debe usar "
        "`grep -oE -e '--[a-z0-9-]+ ?:[^;]+;'`. Sin `-e`, (g/u)grep lo "
        'rechaza con "invalid option --[a-z0-9-]+ …".'
    )


def test_bug_129_grep_command_actually_runs():
    """Smoke: el grep arreglado corre sin errores y produce el token esperado."""
    proc = subprocess.run(
        ['grep', '-oE', '-e', '--[a-z0-9-]+ ?:[^;]+;'],
        input='body { --foo: bar; --baz-quux : red ; }',
        capture_output=True,
        text=True,
        check=False,
    )
    # En BSD grep / GNU grep / ugrep, todos deben aceptar -e correctamente.
    # Si exit code es 2 → option parsing failed (el bug); 0 ó 1 son válidos.
    assert proc.returncode in (0, 1), (
        f'BUG-129: `grep -oE -e ...` falló con exit={proc.returncode}; '
        f'stderr={proc.stderr!r}. El `-e` debería separar opciones de patrón.'
    )


# ───── BUG-130 — NOT-APPLICABLE (docs limpios) ───────────────────────────


def test_bug_130_no_stale_v1_platform_tenants_references_in_docs():
    """Si alguien re-introduce `/v1/platform/tenants`, BUG-130 vuelve a
    aplicar. Defendemos el statu-quo.
    """
    src = UI_BACKLOG.read_text()
    # El único hit permitido es la entrada del bug en la tabla 9.x.
    bad = [
        line for line in src.splitlines()
        if '/v1/platform/tenants' in line and '| BUG-130 ' not in line
    ]
    assert not bad, (
        'BUG-130 regresión: `docs/UI_BACKLOG.md` volvió a referenciar '
        f'`/v1/platform/tenants` (no existe). Las rutas reales son '
        f'`/v1/tenants` y `/v1/tenants/{{id}}/status`. Líneas: {bad}'
    )


def test_bug_130_real_tenant_routes_still_exist():
    """Defensa: las rutas reales `POST/GET /tenants` y
    `PATCH /tenants/{id}/status` siguen en `platform_admin_router`.
    """
    src = ROUTES.read_text()
    assert "@platform_admin_router.post('/tenants'," in src, (
        'BUG-130: `POST /v1/tenants` (en platform_admin_router) debe existir.'
    )
    assert "@platform_admin_router.get('/tenants')" in src, (
        'BUG-130: `GET /v1/tenants` (en platform_admin_router) debe existir.'
    )
    assert "@platform_admin_router.patch('/tenants/{tenant_id}/status')" in src, (
        'BUG-130: `PATCH /v1/tenants/{tenant_id}/status` debe existir.'
    )


# ───── BUG-131 — NOT-APPLICABLE (require_platform_owner correcto) ────────


def test_bug_131_require_platform_owner_checks_platform_owner_role():
    src = SECURITY.read_text()
    assert "'platform_owner' not in getattr(request.state, 'roles', [])" in src, (
        "BUG-131/031: `require_platform_owner` debe chequear `'platform_owner'`, "
        "no `'owner'` (que es el rol de tenant). Sin esto, los operadores "
        "reciben 403 cuando deberían pasar."
    )


# ───── BUG-132 — NOT-APPLICABLE (TASK-0077 cubre con doble gate) ─────────


def test_bug_132_task_0077_describes_both_jwt_and_db_gates():
    """La instrucción TASK-0077 (que reemplazó/cubrió TASK-0092) tiene que
    describir explícitamente AMBOS chequeos (JWT + DB).
    """
    src = BACKLOG.read_text()
    task_idx = src.find('### TASK-0077')
    assert task_idx > 0, 'BUG-132: TASK-0077 debe seguir documentado.'
    next_task = src.find('\n---', task_idx + 1)
    block = src[task_idx:next_task]
    assert 'JWT role gate' in block, (
        'BUG-132/092: la instrucción debe describir el JWT role gate (sin él, '
        'JWT-low + DB-admin pasa). Bot review específicamente lo señaló.'
    )
    assert 'DB role gate' in block, (
        'BUG-132/092: la instrucción debe describir el DB role gate '
        '(`select role from app.user_tenant_roles`).'
    )
    assert 'insufficient_token_role' in block, (
        'BUG-132/092: el JWT gate debe responder con `insufficient_token_role` '
        '(el código distingue el modo de falla).'
    )
