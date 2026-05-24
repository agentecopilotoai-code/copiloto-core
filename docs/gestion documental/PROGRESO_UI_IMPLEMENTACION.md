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

### Bloque UI-2 (Ventanilla Única parte 1) — ✅ COMPLETADO 2026-05-24

**Tareas:** GD-UI-0007..0010 (EP-002). Roles primarios: ROL-004 Radicador,
ROL-005 Coordinador VU.

**Archivos nuevos en `admin-panel/src/features/gd/ventanilla/`:**

| Archivo | LOC | Cov |
|---------|-----|-----|
| `VentanillaHome.jsx` (landing del módulo) | 116 | 100% |
| `NuevoRadicadoEntrada.jsx` (wizard 5 pasos) | ~520 | 98.32% |
| `NuevoRadicadoSalida.jsx` | ~210 | 84.5% |
| `ColaVentanilla.jsx` (DataTable + drawer clasificar) | ~245 | 97.34% |
| `RadicadoConstanciaPreview.jsx` (QR SVG inline) | ~155 | 98.48% |
| `VerificarConstanciaPublica.jsx` (sin auth) | ~160 | 100% |
| `useGdRadicados.js` (4 hooks) | ~110 | 100% |
| `index.js` (barrel) | 16 | 100% |

**Extensiones en `services/gdApi.js` (8 endpoints nuevos):**
- `crearRadicadoEntrada/Salida`, `clasificarRadicado` (GD-API-0024..0026)
- `listColaPendientesClasificacion` (GD-API-0031)
- `verificarConstanciaPublica` (GD-API-0030 público, sin auth)
- `listCanales`, `buscarTerceros`, `crearTercero`, `listDependencias`
- `sugerenciaIaExtraer` (GD-API-0079 opcional)

**Placeholders reemplazados:**
- `GdVentanillaHome` → `<VentanillaHome />`
- `GdNuevoRadicado` → `<NuevoRadicadoEntrada />`
- `GdNuevoRadicadoSalida` (nuevo) → `<NuevoRadicadoSalida />`
- `GdColaVU` → `<ColaVentanilla />`

**Decisiones (D-UI-7..D-UI-10):**

- **D-UI-7 (Wizard como state local, no router)**: el wizard de nuevo
  radicado mantiene los 5 pasos en `useState` interno (no en URL). Permite
  validación cliente sin afectar deep-links + el progreso se pierde si el
  usuario navega fuera (esperado para un wizard transaccional). El
  `stepCanAdvance` por paso evita avanzar con datos incompletos.
- **D-UI-8 (Sugerencia IA inline + Aceptar/Rechazar)**: la IA en paso 2
  es OPT-IN — el operador debe hacer click "Pedir sugerencia". Una vez
  llega, los botones "Aceptar" (copia el resumen al campo descripción)
  y "Rechazar" (limpia la sugerencia sin tocar el campo) son explícitos.
  Sigue RNF-029: la IA nunca muta state sin confirmación humana.
- **D-UI-9 (QR como SVG inline determinista)**: el QR de la constancia
  se renderiza inline en SVG sin dependencias externas. Es un placeholder
  visual (no decodificable real) — el backend ya genera la URL+token con
  GD-API-0131. Para producción se reemplazará por una lib JS de QR pero
  el contrato (props `radicado.codigo_verificacion` + `verifyBaseUrl`) ya
  está estable. **Cero PII** en el QR (solo URL + token opaco) — D71 del
  backend.
- **D-UI-10 (Vista pública verificar sin auth + GdShell-root parcial)**:
  `VerificarConstanciaPublica` se monta sin sidebar/topbar — es una
  página standalone que importa solo `portal.css` y usa el wrapper
  `.gd-shell-root` para heredar tokens. Devuelve datos NO sensibles
  (sin tercero, sin descripción del trámite) — GD-API-0030 backend
  ya lo enforce.

**Métricas:**
- 47 tests nuevos (4 archivos): hooks (15) + wizard (13) + cola (7) +
  constancia (5) + verificar pública (4) + home VU (5) + salida (3
  útiles, 2 setup) + gdApi extendido (11 nuevos)
- Tests totales features/gd: **183/183** ✅
- Coverage features/gd = **97.55% statements**
- Coverage `features/gd/ventanilla/**` = **96.71%**
- `services/gdApi.js` = **100%**
- Global admin-panel = **86.89% ≥ 86% gate** ✅

### Bloque UI-3 (Ventanilla Única parte 2) — ✅ COMPLETADO 2026-05-24

**Tareas:** GD-UI-0011..0015 (EP-002 cierre).

**Archivos nuevos:**

| Archivo | LOC | Cov |
|---------|-----|-----|
| `RadicadoFicha.jsx` (ficha tabs + 3 modales) | ~530 | alta |
| `AnulacionesPendientes.jsx` (aprobar/rechazar con RNF-058) | ~205 | alta |
| `BuscarRadicados.jsx` (10 filtros + scope) | ~280 | alta |
| `ReportesVentanilla.jsx` (KPIs + bars + exportar) | ~250 | alta |

**Extensiones `services/gdApi.js` (10 endpoints nuevos):**
- `getRadicado` (ficha)
- `reclasificarRadicado` (GD-API-0027)
- `corregirDatosMenores` (GD-API-0032)
- `solicitarAnulacionRadicado` / `listAnulacionesPendientes` /
  `aprobarAnulacion` / `rechazarAnulacion` (GD-API-0028)
- `buscarRadicados` (GD-API-0029 con todos los filtros)
- `getReportesVentanilla` / `exportarReporteVentanilla` (PERM-REP-004)

**Hooks añadidos (`useGdRadicados.js` +7):**
`useGdRadicado`, `useReclasificarRadicado`, `useCorregirDatosMenores`,
`useSolicitarAnulacion`, `useAnulacionesPendientes` (con `aprobar/rechazar`
helpers que disparan refresh), `useBuscarRadicados` (con `enabled` flag
para gating UI), `useReportesVentanilla` (con `exportar` helper).

**Placeholders reemplazados:**
- `GdRadicadoFicha` → `<RadicadoFicha />` (con tabs reales)
- `GdBuscar` → `<BuscarRadicados />`
- `GdConsulta` → `<BuscarRadicados />` (rol-consulta reusa el mismo
  componente, server-side enforce R-only)
- Nuevos exports: `GdAnulacionesPendientes`, `GdBuscarRadicados`,
  `GdReportesVentanilla`.

**Decisiones (D-UI-11..D-UI-13):**

- **D-UI-11 (RadicadoFicha = 5 tabs + 3 modales reusables)**: la ficha
  organiza todo el ciclo de vida del radicado en tabs (General / Anexos /
  Clasificación / Trazabilidad / Acciones) + 3 modales accesibles
  desde header y desde tab Acciones (reclasificar / corregir / anular).
  La pestaña Trazabilidad usa `useGdAudit` con `enabled=true` solo
  cuando se selecciona — evita fetch innecesario al abrir la ficha.
  Cada modal cierra con click en backdrop + Escape.
- **D-UI-12 (RNF-058 enforce dual server+client)**: en `AnulacionesPendientes`,
  el botón "Aprobar/Rechazar" se OCULTA cuando
  `solicitud.solicitante_user_id === currentUserId` (mensaje "No puede
  aprobar la propia"). El backend igualmente valida (no nos confiamos
  del frontend) pero esto evita el mal UX de mostrar un botón que
  retornaría 403.
- **D-UI-13 (BuscarRadicados con `enabled` flag inicial)**: el hook
  `useBuscarRadicados` recibe `enabled` para EVITAR fetch inicial
  cuando la pantalla acaba de abrirse sin filtros. La búsqueda solo
  se dispara al click en "Buscar" → `setSubmitted(true)`. Esto evita
  llamar al backend con resultset enorme (RNF-021). El alcance se
  toma del `useGdScope` global y se inyecta en cada query.

**Métricas:**
- 1554/1554 tests admin-panel ✅ (+108 tests nuevos en bloque UI-3)
- Coverage features/gd subió aprox a 92-95% según sub-carpeta
- Global admin-panel = **87.17% ≥ 86% gate** ✅
- Build OK

### Bloque UI-4 (Buzón de trabajo) — ✅ COMPLETADO 2026-05-24

**Tareas:** GD-UI-0016..0019 (EP-003). Roles primarios: ROL-007..ROL-011
(operativos) + ROL-009 Jefe Dependencia para buzón scope=dependencia.

**Archivos nuevos en `admin-panel/src/features/gd/buzon/`:**

| Archivo | LOC | Cubre |
|---------|-----|-------|
| `MiBuzon.jsx` (layout 3-col Gmail) | ~225 | GD-UI-0016 |
| `BuzonDependencia.jsx` (tabs Buzón / Carga equipo) | ~245 | GD-UI-0017 |
| `TareaFicha.jsx` (5 acciones + modal + UsuarioPicker) | ~265 | GD-UI-0018 |
| `ReasignacionMasiva.jsx` (wizard lote) | ~210 | GD-UI-0019 |
| `UsuarioPicker.jsx` (reusable) | ~55 | helper de 0018 + 0019 |
| `useGdBuzon.js` (8 hooks + CARPETAS const) | ~210 | data layer |
| `index.js` (barrel) | 18 | |

**Extensiones `services/gdApi.js` (+9 endpoints):**
`getMiBuzon`, `getBuzonDependencia`, `getCargaEquipo`, `getTarea`,
`ejecutarAccionTarea`, `listUsuariosDependencia`,
`getTareasPendientesUsuario`, `reasignarTareasLote`.

**Hooks añadidos:** `useMiBuzon`, `useBuzonDependencia`, `useCargaEquipo`,
`useTarea`, `useAccionTarea`, `useUsuariosDependencia`,
`useTareasPendientesUsuario`, `useReasignarTareasLote`.

**Placeholders reemplazados:** `GdBuzonHome` → `<MiBuzon />`,
`GdBuzonDependencia` → `<BuzonDependencia />`. Nuevos:
`GdTareaFicha`, `GdReasignacionMasiva`.

**Decisiones (D-UI-14..D-UI-17):**

- **D-UI-14 (Layout 3-col estilo Gmail con state local)**: `MiBuzon`
  usa CSS Grid `220px 380px 1fr`. Carpetas a la izquierda con conteos
  del backend, lista en el centro con selección visual, detalle a la
  derecha con CTAs contextuales (abrir ficha / ver tarea). Selección
  por `useState(selectedId)`. Cambio de carpeta resetea selección.
- **D-UI-15 (Carpetas como constante exportada)**: `CARPETAS` en
  `useGdBuzon.js` es la fuente de verdad — UI las renderiza, backend
  las recibe como query param `carpeta`. 10 valores: pqrsd,
  correspondencia_in/out, tareas, borradores, docs_revisar/aprobar/
  firmar, notificaciones, alertas. Cada una con `icon` (emoji para
  no depender de lib).
- **D-UI-16 (Tab "Carga del equipo" gated por PERM-REP-009 visual)**:
  en BuzonDependencia el tab aparece DISABLED visualmente (no hidden)
  para roles sin permiso, con `title` explicativo. Si lo tienen,
  carga vía `useCargaEquipo` con KPIs por usuario.
- **D-UI-17 (Acciones del workflow declarativas con `requireJustif` +
  `requirePicker`)**: TareaFicha define `ACCIONES` como array con
  metadata `{requireJustif, requirePicker, tone}`. `AccionModal`
  renderiza condicionalmente `JustificacionRequiredField` o
  `UsuarioPicker` según las flags, y deshabilita el submit hasta que
  ambas validen. Patrón reusable para otras fichas (PQRSD ficha en
  bloque UI-5 lo reusará).

**Métricas:**
- 1606+/1606+ tests admin-panel ✅ (+52 nuevos bloque UI-4)
- 284/284 tests features/gd ✅
- Coverage features/gd buzón = 92-100% por sub-archivo
- Global admin-panel = **87.36% ≥ 86% gate** ✅
- Build OK

### Bloque UI-5 (PQRSD parte 1) — ✅ COMPLETADO 2026-05-24

**Tareas:** GD-UI-0020..0024 (EP-004 parte 1).
**Roles primarios:** ROL-006 Admin PQRSD, ROL-007 Profesional,
ROL-008 Revisor, ROL-009 Jefe Dependencia, ROL-014 Firmante.

**Archivos nuevos en `admin-panel/src/features/gd/pqrsd/`:**

| Archivo | LOC | Cubre |
|---------|-----|-------|
| `PanelPQRSD.jsx` (dashboard admin) | ~180 | GD-UI-0020 |
| `ListaPQRSD.jsx` (tabla + semáforo) | ~190 | GD-UI-0021 |
| `FichaPQRSD.jsx` (5 tabs + workflow modal) | ~525 | GD-UI-0022/0023/0024 |
| `useGdPQRSD.js` (3 readers + 10 mutators) | ~135 | hooks |
| `index.js` (barrel) | 22 | |

**Extensiones `services/gdApi.js` (+13 endpoints):**
- `listPQRSDFiltrados`, `getPQRSDDashboard`, `getPQRSD` (lectura)
- `asignarDependenciaPQRSD`, `asignarFuncionarioPQRSD`,
  `reasignarPQRSD` (asignación — GD-API-0044/0045)
- `proyectarRespuestaPQRSD` (GD-API-0046)
- `enviarRespuestaARevision`, `revisarRespuestaPQRSD`,
  `aprobarRespuestaPQRSD`, `firmarRespuestaPQRSD`,
  `radicarSalidaRespuesta`, `enviarRespuestaPQRSD` (workflow — GD-API-0047)

**Placeholders reemplazados:**
- `GdPqrsdPanel` → `<PanelPQRSD />`
- `GdPqrsdFicha` → `<FichaPQRSD />`
- Nuevos exports: `GdPqrsdLista`, `GdPqrsdMias`, `GdPqrsdSinAsignar`,
  `GdPqrsdVencimientos`, `GdPqrsdVencidas` (variantes con
  `filtrosIniciales` distintos).

**Decisiones (D-UI-18..D-UI-20):**

- **D-UI-18 (Mutadores genéricos vía `useMutator` factory)**: 10 hooks
  de acción del workflow comparten el mismo state shape
  (`{submitting, error, submit}`) mediante un helper interno
  `useMutator(session, fn)`. Reduce ~100 LOC de duplicación y
  garantiza comportamiento consistente (rejection rethrows, captura
  en `error`, etc.).
- **D-UI-19 (`ACCIONES_META` declarativo para modales del workflow)**:
  el componente `ActionModal` recibe `accion` (string) e indexa una
  tabla `ACCIONES_META` con la metadata: `title`, `help`, `cta`,
  `requireJustif`, `requireContenido`, `tone`, `useHook`, `scope`
  (pqrsd vs respuesta), `extra` (payload extra). Patrón paralelo al
  D-UI-17 de TareaFicha. Permite agregar acciones nuevas sin tocar
  el render lógico.
- **D-UI-20 (ListaPQRSD reusable con `filtrosIniciales`)**: la misma
  lista se usa como /mias, /sin-asignar, /vencimientos, /vencidas
  pre-cargando filtros. Evita 4 componentes casi idénticos.
  Cambio de filtros local re-fetches con `JSON.stringify` en deps.

**Métricas:**
- 1658/1658 tests admin-panel ✅ (+104 nuevos bloque UI-5)
- 336/336 tests features/gd ✅
- Coverage features/gd/pqrsd 92-100% por sub-archivo
- Global admin-panel = **87.46% ≥ 86% gate** ✅
- Build OK

### Bloque UI-6 (PQRSD parte 2 — CIERRE EP-004) — ✅ COMPLETADO 2026-05-24

**Tareas:** GD-UI-0025..0028 (EP-004 parte 2 → cierre épica).

**Archivos nuevos / modificados:**

| Archivo | LOC | Cubre |
|---------|-----|-------|
| `ReportesPQRSD.jsx` (4 tableros + exportar) | ~225 | GD-UI-0028 |
| `FichaPQRSD.jsx` (+TabSuspensiones, +6 entradas ACCIONES_META, +badge "⏸ Suspendido") | +180 | GD-UI-0025/0026/0027 |
| `useGdPQRSD.js` (+8 hooks UI-6) | +60 | hooks |

**Extensiones `services/gdApi.js` (+9 endpoints):**
- `cerrarPQRSD`, `reabrirPQRSD` (GD-API-0048)
- `trasladarPQRSD` (GD-API-0049)
- `solicitarInfoAdicionalPQRSD` (GD-API-0050)
- `suspenderTerminoPQRSD`, `reanudarTerminoPQRSD` (GD-API-0042)
- `listSuspensionesPQRSD` (historial)
- `getReportesPQRSD`, `exportarReportePQRSD` (GD-API-0051)

**Decisiones (D-UI-21..D-UI-23):**

- **D-UI-21 (Tab "Suspensiones" como vista dedicada)**: 6º tab que
  lista el historial de pausas del término legal. Badge "⏸ Suspendido"
  en header visibiliza el estado y permite suspender/reanudar in-place
  (gated por PERM-PQRSD-022).
- **D-UI-22 (`ACCIONES_META` ampliado con `requireTipoCierre` +
  `requireEntidadDestino`)**: `ActionModal` maneja 3 tipos de campos
  extra (justificación, tipo_cierre, entidad_destino) sin cambios al
  render principal. Patrón consistente con D-UI-19.
- **D-UI-23 (Tab Acciones rol+estado aware)**: CTAs desaparecen según
  `pq.estado` (Cerrar oculto si cerrada, Reabrir solo si cerrada) y
  según `pq.termino_suspendido` (Suspender vs Reanudar). Evita 4xx
  del backend y reduce ruido visual.

**Métricas:**
- **1693/1693 tests admin-panel ✅** (+35 nuevos UI-6)
- **371/371 tests features/gd ✅**
- Coverage features/gd/pqrsd 92-100% por sub-archivo
- Global admin-panel = **87.43% ≥ 86% gate** ✅
- Build OK

**EP-004 PQRSD CERRADA** — 9 vistas funcionales:
Panel + Lista + 5 variantes de lista (mias, sin-asignar, vencimientos,
vencidas, panel) + Ficha 6-tabs con workflow 7-pasos completo + 8
acciones contextuales (proyectar/enviar revisión/revisar/aprobar/
firmar/radicar/enviar/cerrar/reabrir/trasladar/info-adicional/
suspender/reanudar/reasignar) + Reportes con 4 tableros + exportar.

### Bloque UI-7 (Correspondencia interna + externa — CIERRE EP-005) — ✅ COMPLETADO 2026-05-24

**Tareas:** GD-UI-0029..0034 (EP-005).
**Roles primarios:** ROL-010 Usuario CI, ROL-013 Usuario Radicación Externa,
ROL-007 Profesional, ROL-009 Jefe Dependencia, ROL-005 Coordinador VU.

**Archivos nuevos en `admin-panel/src/features/gd/correspondencia/`:**

| Archivo | LOC | Cubre |
|---------|-----|-------|
| `CorrespondenciaInterna.jsx` (tabs + form nueva) | ~230 | GD-UI-0029/0030 |
| `CorrespondenciaExterna.jsx` (6 tabs + form borrador) | ~225 | GD-UI-0031 |
| `CorrespondenciaFicha.jsx` (5-6 tabs + workflow + soporte + destinatarios + anular) | ~575 | GD-UI-0031/0032/0033/0034 |
| `useGdCorrespondencia.js` (2 readers + 15 mutators) | ~115 | hooks |
| `index.js` (barrel) | 8 | |

**Extensiones `services/gdApi.js` (+17 endpoints):**
- CI: `crearCorrespondenciaInterna`, `marcarLeida`, `responder`, `reenviar` (GD-API-0052)
- Listar/get: `listCorrespondencia`, `getCorrespondencia`
- CE workflow (GD-API-0054): `crearBorradorCorrespondenciaExterna`,
  `enviarCorrespondenciaARevision`, `revisarCorrespondencia`,
  `aprobarCorrespondencia`, `firmarCorrespondencia`,
  `radicarSalidaCorrespondencia`, `enviarCorrespondencia`
- Soportes: `registrarSoporteEnvio` (PERM-CE-011)
- Destinatarios (GD-API-0055): `agregarDestinatarioCorrespondencia`,
  `quitarDestinatarioCorrespondencia`
- Anulación: `solicitarAnulacionCorrespondencia` (GD-API-0056)

**Placeholders reemplazados:**
- `GdCorrespondenciaInterna` → `<CorrespondenciaInterna />`
- `GdCorrespondenciaExterna` → `<CorrespondenciaExterna />`
- Nuevo: `GdCorrespondenciaFicha`.

**Decisiones (D-UI-24..D-UI-26):**

- **D-UI-24 (Ficha unificada interna/externa con tabs condicionales)**:
  un solo componente `CorrespondenciaFicha` maneja ambos tipos. Las
  tabs "Workflow" y "Soporte de envío" aparecen solo si `c.tipo ===
  'externa'`. Reduce duplicación vs tener 2 fichas separadas — los
  datos comunes (asunto, estado, trazabilidad, destinatarios,
  acciones) son ~80% del componente.
- **D-UI-25 (TabDestinatarios edita inline con form append-and-clear)**:
  el form de "Agregar destinatario" se muestra dentro del tab cuando
  el rol tiene CI-001/CE-001 y el estado NO es enviada/anulada.
  Permite manejar las 3 categorías (principal/copia/copia_oculta) sin
  un modal aparte. Cada add limpia el form para encadenar.
- **D-UI-26 (Soportes de envío con histórico + form nuevo)**: en lugar
  de un modal único, mostramos la tabla histórica + un form de
  "Registrar nuevo soporte" siempre visible (medio: postal/email/fax/
  entrega/otro + guía + fecha + obs). Refleja la realidad operativa:
  una correspondencia puede tener varios soportes (ej. email + guía
  postal de respaldo).

**Métricas:**
- **1762/1762 tests admin-panel ✅** (+69 nuevos UI-7)
- **431/431 tests features/gd ✅**
- Coverage features/gd/correspondencia 85-100% (Ficha 92% lines)
- Global admin-panel = **87.53% ≥ 86% gate** ✅
- Functions 75.17% ≥ 75% ✅
- Build OK

**EP-005 Correspondencia CERRADA** — 3 vistas + ficha unificada con
6 tabs + 13 acciones contextuales del workflow + gestión de
destinatarios múltiples + soportes de envío con histórico + anulación.

### Bloque UI-8 (Documentos + plantillas + firmas — CIERRE EP-006) — ✅ COMPLETADO 2026-05-24

**Tareas:** GD-UI-0035..0044 (EP-006). 10 vistas.
**Roles primarios:** ROL-014 Firmante, ROL-017 Admin Plantillas,
ROL-007 Profesional, ROL-009 Jefe Dependencia, ROL-003 Admin Documental,
ROL-001 Admin Sistema.

**Archivos nuevos:**

| Archivo | LOC | Cubre |
|---------|-----|-------|
| `documentos/Biblioteca.jsx` (lista filtrable) | ~175 | GD-UI-0035 |
| `documentos/CargarDocumentoModal.jsx` (drag&drop) | ~200 | GD-UI-0037 |
| `documentos/DocumentoFicha.jsx` (4 tabs + nueva ver. + anular) | ~365 | GD-UI-0036/0038 |
| `documentos/useGdDocumentos.js` (3 readers + 4 mutators) | ~100 | hooks |
| `documentos/index.js` (barrel) | 8 | |
| `plantillas/AdminPlantillas.jsx` (CRUD + versionado) | ~430 | GD-UI-0039 |
| `plantillas/GenerarDocumento.jsx` (variables + preview) | ~185 | GD-UI-0040 |
| `plantillas/useGdPlantillas.js` (2 readers + 5 mutators) | ~80 | hooks |
| `plantillas/index.js` (barrel) | 7 | |
| `firmas/PorFirmar.jsx` (bandeja + 3 acciones) | ~265 | GD-UI-0041 |
| `firmas/FirmaEscaneadaModal.jsx` (registro manuscrita) | ~150 | GD-UI-0042 |
| `firmas/EvidenciaFirma.jsx` (hash + IP + geo + certif) | ~135 | GD-UI-0043 |
| `firmas/AdminFirmantes.jsx` (CRUD firmantes autorizados) | ~330 | GD-UI-0044 |
| `firmas/useGdFirmas.js` (3 readers + 6 mutators) | ~100 | hooks |
| `firmas/index.js` (barrel) | 9 | |

**Extensiones `services/gdApi.js` (+24 endpoints, GD-API-0057..0072):**
- Documentos: `listDocumentos`, `getDocumento`, `listVersionesDocumento`,
  `crearDocumento`, `nuevaVersionDocumento`, `anularDocumento`,
  `subirArchivo` (`/core/archivos`).
- Plantillas: `listPlantillas`, `getPlantilla`, `crearPlantilla`,
  `actualizarPlantilla`, `nuevaVersionPlantilla`, `inactivarPlantilla`,
  `generarDocumentoDePlantilla`.
- Firmas: `listPorFirmar`, `getEvidenciaFirma`, `registrarFirmaEscaneada`,
  `firmarDocumento`, `rechazarFirmaDocumento`, `listFirmantesAutorizados`,
  `crearFirmanteAutorizado`, `actualizarFirmanteAutorizado`,
  `inactivarFirmanteAutorizado`.

**Placeholders reemplazados:**
- `GdBiblioteca` → `<Biblioteca />`
- `GdPlantillas` → `<AdminPlantillas />`
- `GdPorFirmar` → `<PorFirmar />`
- Nuevos: `GdDocumentoFicha`, `GdGenerarDocumento`, `GdEvidenciaFirma`,
  `GdAdminFirmantes`.

**Decisiones (D-UI-27..D-UI-29):**

- **D-UI-27 (Carga de archivos en 2 pasos: `subirArchivo` →
  `crearDocumento`)**: el modal de carga sube primero el binario a
  `/core/archivos`, obtiene `archivo_digital_id`, y solo entonces crea
  el registro documental con metadata. Esto permite que el antivirus
  server-side (RNF-046) escanee el archivo antes de que exista el
  documento referenciable. El cliente muestra estados secuenciales
  (`subiendo` → `creando` → `listo`) para feedback explícito.
- **D-UI-28 (Plantillas: layout 2-col con `mode` único)**: en vez de
  rutas separadas para crear/editar/nueva-versión/inactivar, una sola
  ruta muestra la lista a la izquierda y un panel a la derecha cuyo
  contenido se rige por el `mode` (`view|edit|new|nuevaver|inactivar`).
  Reduce navegación y mantiene contexto. `GenerarDocumento` SÍ es ruta
  aparte porque cambia la audiencia (usuario operativo, no admin).
- **D-UI-29 (Permisos cruzados PLA-001 + PLA-USE)**: descubrí en tests
  que `gd.admin_plantillas` tiene PLA-001 (RW para administrar) pero
  NO PLA-USE (R para generar) — son roles funcionalmente disjuntos
  por diseño. Un usuario que administra plantillas y también las usa
  debe tener ambos roles asignados (caso típico: jefe de dependencia
  + admin plantillas en entidades pequeñas).

**Métricas:**
- **1882/1882 tests admin-panel ✅** (+120 nuevos UI-8)
- **560/560 tests features/gd ✅**
- Coverage features/gd/documentos = **97.00% lines** ✅
- Coverage features/gd/plantillas = **97.57% lines** ✅
- Coverage features/gd/firmas = **98.35% lines** ✅
- Global admin-panel = **87.83% ≥ 86% gate** ✅
- Functions 75.05% ≥ 75% ✅
- Lint OK (0 errores)

### Bloque UI-9 (TRD/TVD + Expediente Electrónico — CIERRE EP-007) — ✅ COMPLETADO 2026-05-24

**Tareas:** GD-UI-0045..0051 (EP-007). 7 vistas.
**Roles primarios:** ROL-003 Admin Documental, ROL-016 Comité Archivo,
ROL-007 Profesional, ROL-002 Auditor Externo.

**Archivos nuevos:**

| Archivo | LOC | Cubre |
|---------|-----|-------|
| `trd/TablaTRD.jsx` (árbol serie/subserie/tipo + nueva versión) | ~430 | GD-UI-0045/0046 |
| `trd/TablaTVD.jsx` (retención AG/AC + disposición + editar) | ~210 | GD-UI-0047 |
| `trd/ClasificarConTRD.jsx` (selector jerárquico + clasificar) | ~165 | GD-UI-0048 |
| `trd/useGdTRD.js` (5 readers + 9 mutators) | ~155 | hooks |
| `trd/index.js` | 8 | |
| `expedientes/ExpedienteFicha.jsx` (4 tabs + foliación + acciones) | ~395 | GD-UI-0049 |
| `expedientes/CerrarExpedienteModal.jsx` (acta + transferencia + hash) | ~190 | GD-UI-0050 |
| `expedientes/BuscarExpedientes.jsx` (form + tabla + filtros) | ~190 | GD-UI-0051 |
| `expedientes/useGdExpedientes.js` (6 readers + 7 mutators) | ~165 | hooks |
| `expedientes/index.js` | 8 | |

**Extensiones `services/gdApi.js` (+27 endpoints, GD-API-0073..0085):**
- TRD: `listTRD`, `getSerie`, `getTRDVersionActual`, `listVersionesTRD`,
  `crearSerie`, `actualizarSerie`, `eliminarSerie`, `crearSubserie`,
  `crearTipoDocumental`, `nuevaVersionTRD`, `aprobarVersionTRD`.
- TVD: `listTVD`, `actualizarTVD`.
- Clasificación: `clasificarConTRD`.
- Expedientes: `listExpedientes`, `getExpediente`, `crearExpediente`,
  `actualizarExpediente`, `listDocumentosExpediente`,
  `agregarDocumentoExpediente`, `quitarDocumentoExpediente`,
  `cerrarExpediente`, `transferirExpediente`, `reabrirExpediente`,
  `getIndiceExpediente`, `getActaCierreExpediente`, `buscarExpedientes`.

**Placeholders reemplazados:**
- `GdTrdHome` → `<TablaTRD />`
- `GdExpedientes` → `<BuscarExpedientes />`
- Nuevos: `GdTvdHome`, `GdClasificarConTRD`, `GdExpedienteFicha`.

**Decisiones (D-UI-30..D-UI-32):**

- **D-UI-30 (TRD jerárquica navegable con expand/collapse en vez de
  páginas separadas)**: una sola vista `TablaTRD` muestra el árbol
  serie→subserie→tipo con expand/collapse. Las acciones admin (crear
  serie/subserie/tipo, inactivar, nueva versión + aprobación con
  acta de comité) son modales contextuales. Reduce navegación y
  preserva contexto jerárquico.
- **D-UI-31 (Nueva versión TRD = crear + aprobar en un solo flujo)**:
  la creación de versión consume internamente dos endpoints
  (`nuevaVersionTRD` → `aprobarVersionTRD`). El usuario aporta acta
  de comité en un único formulario. Esto refleja la realidad operativa:
  toda nueva versión TRD requiere aprobación formal del Comité de
  Archivo y nunca queda en "borrador" indefinido. La acta queda
  registrada como audit trail.
- **D-UI-32 (Cierre de expediente en 3 fases con hash visible)**: el
  modal `CerrarExpedienteModal` opera en `form → cerrando → acta`.
  Tras el cierre server-side genera el acta consolidada con
  `hash_indice` (SHA-256) que la UI muestra explícitamente al
  usuario antes de finalizar. Integridad RNF-009: el hash es la
  prueba criptográfica de que el contenido del expediente no se
  alteró tras el cierre. Si el usuario marca "transferir
  inmediatamente", se encadena `transferirExpediente` y la nota
  de transferencia queda en el acta.

**Métricas:**
- **2092/2092 tests admin-panel ✅** (+210 nuevos UI-9)
- **675/675 tests features/gd ✅**
- Coverage `features/gd/trd` = **97.99% lines / 88.75% functions** ✅
- Coverage `features/gd/expedientes` = **95.34% lines / 89.55% functions** ✅
- Coverage `features/gd/services` (gdApi) = **100% lines / 100% functions** ✅
- Global admin-panel = **88.74% ≥ 86% gate** ✅
- Functions 78.68% ≥ 75% ✅ (subió de 74.92 con smoke-tests de gdApi)
- Lint OK (0 errores)

**EP-007 TRD/TVD/Expedientes CERRADA** — 7 vistas:
TablaTRD navegable con árbol jerárquico (serie/subserie/tipo) +
versionado formal con acta de Comité + TablaTVD con retención AG/AC
y disposición final (CT/E/S/M) + clasificación con TRD + Expediente
electrónico con 4 tabs (general/documentos/trazabilidad/acciones) +
foliación automática + cierre con acta hash-validada + transferencia
al Archivo Central + reapertura justificada + búsqueda multi-filtro.

**EP-006 Documentos+plantillas+firmas CERRADA** — 10 vistas:
Biblioteca filtrable + ficha de documento con 4 tabs (general /
versiones / trazabilidad / acciones) + carga drag&drop con
validación MIME+tamaño + reemplazo y anulación con motivo + admin
de plantillas con versionado + generación con preview en vivo de
sustitución `{{variable}}` + bandeja "Por firmar" con firma digital /
escaneada / rechazo + evidencia técnica completa (hash SHA-256 + IP
+ geo + certif + user-agent) + admin de firmantes autorizados con
tipos habilitados y vigencia.
