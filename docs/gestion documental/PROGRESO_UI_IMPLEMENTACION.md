# Progreso de implementación — UI Módulo Gestión Documental

> Bitácora del loop iterativo de implementación de las 94 tareas
> `GD-UI-0001..0094` del `UI_BACKLOG.md` distribuidas en 13 épicas
> EP-001..EP-013. Cada bloque cierra con commit + push + ScheduleWakeup
> para el siguiente, hasta cubrir las 94 tareas.

## Convenciones de la UI GD

1. **Heredar tokens base** de `admin-panel/src/styles/tokens.css` pero
   scope-specific overrides en `src/features/gd/styles/gd-tokens.css`
   para emular el design system del portal (slate + sky + Source Serif).
   Aplicado vía clase `.gd-shell` raíz del módulo (no contaminamos el
   admin-panel principal).
2. **Permisos GD** en `src/permissions/gd-matrix.js` con los 19 roles
   GD × ~140 permisos derivados de `MATRIZ_PERMISOS.md`. Wrapper
   `<GdRouteGuard requires=[] alcance=>` paralelo al `<RequirePermission/>`
   existente.
3. **Layout módulo GD**: `<GdShell />` con sidebar contextual al rol
   + topbar (búsqueda + ScopeSelector + user chip) + breadcrumbs +
   content. Mismo patrón que `InfluencerShell`.
4. **Componentes de dominio reutilizables** en `src/features/gd/components/`:
   `RadicadoCard`, `PQRSDStatusChip`, `TerminoVencimientoBadge`,
   `WorkflowTimeline`, `JustificacionRequiredField`, `DependenciaPicker`,
   `UsuarioPicker`, `SerieSubseriePicker`, `IASuggestionInline`,
   `InstitutionalLetterhead`.
5. **Tests vitest + testing-library** ≥ 90% coverage de cada feature
   nueva (`features/gd/**/*.jsx`).
6. **Sin DELETE en UI**. Acciones legales: anular / inactivar / cerrar
   vigencia / reasignar / versionar.
7. **Lenguaje formal** ("Se ha radicado", no "¡Listo!"). Estado de
   Colombia — la app la lee el ciudadano en constancias.
8. **Cero PII en URL**. Solo UUIDs.

## Plan de bloques (15 bloques cubren las 94 tareas)

| Bloque | Tareas | Épica | Foco |
|--------|--------|-------|------|
| UI-1   | GD-UI-0001..0006 | EP-001 | Foundation: matriz perms + GdShell + tokens + componentes dominio + useGdAudit |
| UI-2   | GD-UI-0007..0010 | EP-002 | Ventanilla: nuevo radicado entrada/salida + cola + constancia QR |
| UI-3   | GD-UI-0011..0015 | EP-002 | Ventanilla: anulación + reclasif + búsqueda + reportes + ficha |
| UI-4   | GD-UI-0016..0019 | EP-003 | Buzón: mi buzón + dep + tarea + reasignación masiva |
| UI-5   | GD-UI-0020..0024 | EP-004 | PQRSD parte 1: panel + lista + ficha + workflow proyección + revisar |
| UI-6   | GD-UI-0025..0028 | EP-004 | PQRSD parte 2: cierre + traslado + suspensión + reportes |
| UI-7   | GD-UI-0029..0034 | EP-005 | Correspondencia interna + externa + soportes + dest múltiples + anular |
| UI-8   | GD-UI-0035..0044 | EP-006 | Documentos + plantillas + firmas (10 vistas) |
| UI-9   | GD-UI-0045..0051 | EP-007 | TRD/TVD + clasificación + expediente |
| UI-10  | GD-UI-0052..0066 | EP-008 | Admin sistema (15 vistas: entidad, estructura, cargos, catalogs, calendar, params, users, roles, política, sesiones, mail, ia, identidades, reglas) |
| UI-11  | GD-UI-0067..0071 | EP-009 | Auditoría + reportes + dashboard auditor + trazabilidad + IA usage |
| UI-12  | GD-UI-0072..0078 | EP-010 | IA componentes embebidos en flujos (sugerencias, borradores, dedupe, extracción correo) |
| UI-13  | GD-UI-0079..0086 | EP-011/012 | Correo institucional + notificaciones + alertas |
| UI-14  | GD-UI-0087..0090 | EP-013 | Periféricos parte 1: admin + puntos + impresión etiqueta + digitalización individual |
| UI-15  | GD-UI-0091..0094 | EP-013 | Periféricos parte 2: lote + reimpresión + bandeja escaneos huérfanos + dashboard salud |

---

## Bloques completados

### Bloque UI-1 (foundation) — ✅ COMPLETADO 2026-05-24

**Tareas:** GD-UI-0001..0006 (EP-001).

**Archivos nuevos:**

| Archivo | LOC | Cov |
|---------|-----|-----|
| `admin-panel/src/permissions/gd-matrix.js` | ~260 | 100% |
| `admin-panel/src/features/gd/styles/portal.css` | 1083 | (visual) |
| `admin-panel/src/features/gd/shell/GdShell.jsx` | 103 | 92% |
| `admin-panel/src/features/gd/shell/GdSidebar.jsx` | 135 | 100% |
| `admin-panel/src/features/gd/shell/GdTopBar.jsx` | 95 | 98.7% |
| `admin-panel/src/features/gd/landing/GdLanding.jsx` | 87 | 100% |
| `admin-panel/src/features/gd/components/RadicadoCard.jsx` | 105 | 97.6% |
| `admin-panel/src/features/gd/components/PQRSDStatusChip.jsx` | 37 | 100% |
| `admin-panel/src/features/gd/components/TerminoVencimientoBadge.jsx` | 80 | 100% |
| `admin-panel/src/features/gd/components/WorkflowTimeline.jsx` | 132 | 98.2% |
| `admin-panel/src/features/gd/components/JustificacionRequiredField.jsx` | 73 | 100% |
| `admin-panel/src/features/gd/components/InstitutionalLetterhead.jsx` | 88 | 100% |
| `admin-panel/src/features/gd/hooks/useGdScope.js` | 62 | 92.9% |
| `admin-panel/src/features/gd/hooks/useGdAudit.js` | 39 | 100% |
| `admin-panel/src/features/gd/services/gdApi.js` | 124 | 100% |
| `admin-panel/src/features/gd/placeholders/index.jsx` | 150 | 100% |

**Registros en el shell del admin-panel:**
- `modules.js` + `moduleRegistry.js` + `matrix.js` añaden el item top-level `gd-entry` con capability `gd.module.access` (manager+).
- `rolesAclData.js` añade grupo "Módulo Gestión Documental" en la vista del Platform Owner.

**Decisiones (D-UI-1..D-UI-6):**

- **D-UI-1 (Matriz GD paralela)**: la matriz del módulo principal (`matrix.js`)
  decide visibilidad del item top-level con `gd.module.access`. Una vez dentro
  del GdShell, las 17 capabilities UI-relevantes de los 19 roles GD viven en
  `gd-matrix.js`. Helpers `gdCan`/`gdCanAny`/`gdLandingFor`/`hasAnyGdAccess`.
- **D-UI-2 (Tokens scoped a `.gd-shell-root`)**: copiamos `portal.css` del
  diseñador con un único cambio: el reset `*` + `body` global se redirigió a
  `.gd-shell-root` y descendientes para no contaminar el admin-panel
  principal. Los tokens (`--slate-*`, `--sky-*`, `--font-display`) no chocan
  con `tokens.css` porque los nombres son diferentes.
- **D-UI-3 (ScopeSelector global con persistencia por tenant)**: `useGdScope`
  usa `localStorage` keyed por tenant (`gd_scope__<slug>`). 3 valores
  ('propio' | 'dependencias_autorizadas' | 'institucional'). Todas las
  queries lo pasan al backend que evalúa server-side con `gd.asignacion_alcance`.
- **D-UI-4 (Sidebar rol-aware)**: NAV declarativo + filtro por
  `gdCanAny(roles, perm, 'R')` por cada item. Items y grupos vacíos se ocultan.
  Match parcial de `currentPath` para activar el item correcto en sub-rutas.
- **D-UI-5 (Cliente API GD separado)**: `gdApi.js` apunta a `/api/v1/gd/*` y
  `/api/v1/core/*` (no `/admin/api/core/v1` del producto principal). Detecta
  el error `gd_profile_missing_or_inactive` para mostrar UX de
  "Solicite activación al administrador".
- **D-UI-6 (Placeholders navegables desde el día 1)**: 25 placeholders en
  `placeholders/index.jsx` envuelven el `GdShell` con título + mensaje
  "Vista en construcción". Sirven para que deep-links no rompan y para
  validar la navegación antes de implementar cada vista.

**Métricas:**
- 140 tests nuevos (113 features GD + 16 matriz + 11 placeholders+gdApi/etc)
- Coverage del módulo: **`features/gd/**` 92-100%**, `gd-matrix.js` 100%
- Global admin-panel: **86.49% ≥ 86% gate** ✅
- 1446/1446 tests admin-panel ✅
- Build OK
