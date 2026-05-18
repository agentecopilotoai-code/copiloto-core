"""Fix-group 15: BUG-093..BUG-097.

- BUG-093: VIGENTE. `GoLiveReadiness` no aceptaba `onGoToEscalation` que
  el router le pasa; los checks `handoff`/`policy_engine` pendientes no
  mostraban el CTA de remediation. Fix: aceptar la prop y renderizar
  `<button>Ir a Escalamiento</button>` cuando aplica.
- BUG-094: VIGENTE. `GoLiveReadiness` no permitía refresh manual; el
  operador tenía que reload la página completa. Fix: nuevo estado
  `reloadToken` + botón "Refrescar" en el PageHeader.
- BUG-095: VIGENTE. `dismiss(id)` solo filtraba `visible`; toasts en
  `queueRef.current` no se eliminaban → se promovían después como si
  nunca hubieras cancelado. Fix: filter también queueRef.
- BUG-096: PENDING-INFRA. `brand_logo_url = stored.source_uri` produce
  `file://...` o `s3://...` que el browser no carga. Fix completo
  requiere un endpoint público que sirva el media — deferido.
- BUG-097: VIGENTE. `<ErrorBoundary>` en TenantShell no se resetea al
  cambiar de módulo. Fix: `key={activeModuleId}` fuerza unmount/remount.
"""
from __future__ import annotations

from pathlib import Path


GO_LIVE = Path('admin-panel/src/features/owner-admin/readiness/GoLiveReadiness.jsx')
TOAST = Path('admin-panel/src/components/ui/Toast.jsx')
TENANT_SHELL = Path('admin-panel/src/app/shells/TenantShell.jsx')


# ───── BUG-093 — GoLive onGoToEscalation ────────────────────────────────


def test_bug_093_go_live_accepts_on_go_to_escalation_prop():
    src = GO_LIVE.read_text()
    assert 'onGoToEscalation' in src, (
        'BUG-093: `GoLiveReadiness` debe aceptar y propagar la prop '
        '`onGoToEscalation` que el router le pasa.'
    )
    assert 'ESCALATION_CHECK_KEYS' in src, (
        'BUG-093: debe existir un set de keys que disparan el CTA '
        '(handoff, policy_engine) — fuente de verdad.'
    )
    assert 'Ir a Escalamiento' in src, (
        'BUG-093: el CTA "Ir a Escalamiento" debe rendererse cuando el '
        'check está pending Y onGoToEscalation está disponible.'
    )


# ───── BUG-094 — GoLive manual refresh ──────────────────────────────────


def test_bug_094_go_live_has_manual_refresh():
    src = GO_LIVE.read_text()
    assert 'reloadToken' in src, (
        'BUG-094: `GoLiveReadiness` debe tener un state `reloadToken` que '
        'el botón Refrescar bumpea para forzar re-fetch.'
    )
    assert "'Refrescar'" in src or '>Refrescar<' in src, (
        'BUG-094: debe existir el botón "Refrescar" en el PageHeader.'
    )
    # El effect debe depender de reloadToken.
    assert 'reloadToken' in src and ', reloadToken]' in src, (
        'BUG-094: el `useEffect` que llama `getTenantReadiness` debe '
        'depender de `reloadToken` para que el botón dispare el re-fetch.'
    )


# ───── BUG-095 — Toast queueRef ─────────────────────────────────────────


def test_bug_095_dismiss_drains_queue_ref_too():
    src = TOAST.read_text()
    assert 'queueRef.current = queueRef.current.filter' in src, (
        'BUG-095: `dismiss(id)` debe filtrar también `queueRef.current`. '
        'Antes solo filtraba `visible`; toasts en cola se promovían '
        'después como si nunca hubieras cancelado.'
    )


# ───── BUG-096 — PENDING-INFRA ──────────────────────────────────────────


def test_bug_096_brand_logo_url_pending_infra_documented():
    """Marker: el bug requiere un endpoint público que sirva el media
    para convertir `file://...` / `s3://...` a una URL browser-loadable.
    Cuando se implemente, actualizar este test y catalog.
    """
    src = Path('app/api/v1/routes.py').read_text()
    assert 'stored.source_uri' in src, (
        'BUG-096: si reemplazás `stored.source_uri` por una URL pública '
        '(media proxy / presigned), actualizá el catalog (BUG-096 → DONE).'
    )


# ───── BUG-097 — ErrorBoundary key ──────────────────────────────────────


def test_bug_097_error_boundary_resets_per_module():
    src = TENANT_SHELL.read_text()
    assert 'ErrorBoundary key={activeModuleId}' in src, (
        'BUG-097: `<ErrorBoundary>` en TenantShell debe llevar '
        '`key={activeModuleId}` para que React unmount/remount al navegar '
        'entre módulos. Sin el key, el `error` capturado en módulo A '
        'persiste cuando el usuario abre módulo B.'
    )
