# UI Backlog — CopilotoIA Admin Panel (rediseño por rol)

> Archivo separado de `docs/BACKLOG.md` (operativo) para concentrar **exclusivamente** las tareas de UI derivadas del rediseño en `docs/HTML DESIGN/`. Numeración propia con prefijo `UI-####` para no chocar con `TASK-####`.

---

## 0. Veredicto de readiness para producción (basado en `docs/DONE.md`)

Se revisaron las 86 tareas completadas (TASK-0001 → TASK-0086) y la auditoría de seguridad (25 bugs consolidados en 10 fixes estructurales, todos en DONE):

| Eje | Estado | Evidencia en DONE |
|---|---|---|
| Infraestructura multitenant (RLS, RBAC, Auth0, MFA) | ✅ Producción | TASK-0001, TASK-0016, TASK-0077, TASK-0080 |
| WhatsApp + Instagram/Messenger + Widget Web | ✅ Producción | TASK-0004, TASK-0070, TASK-0074, TASK-0081 |
| RAG con embeddings reales + LLM cloud (Claude/OpenAI) | ✅ Producción | TASK-0005..0007, TASK-0024, TASK-0025, TASK-0078 |
| Booking + recordatorios + reducción no-show + post-cita | ✅ Producción | TASK-0030, TASK-0035, TASK-0036, TASK-0042..0045, TASK-0056 |
| CRM + segmentos + campañas + funnel + medios + paquetes + suscripciones | ✅ Producción | TASK-0037, TASK-0038, TASK-0046..0048, TASK-0051, TASK-0075 |
| Pagos (Stripe + MercadoPago) fail-closed | ✅ Producción | TASK-0040, TASK-0083, TASK-0084 |
| Multi-sede + i18n + tono del bot + recall + referidos | ✅ Producción | TASK-0049, TASK-0050, TASK-0052, TASK-0055, TASK-0071, TASK-0073 |
| Observabilidad + rate limit + DLQ + runbooks + backups | ✅ Producción | TASK-0059, TASK-0060, TASK-0064..0066, TASK-0029 |
| Tests E2E + carga + SLA + consentimiento + retención GDPR | ✅ Producción | TASK-0061..0063, TASK-0072 |
| Legal por tenant + auditoría + go-live readiness | ✅ Producción | TASK-0011, TASK-0018, TASK-0076 |
| Equipo + onboarding self-service | ✅ Producción | TASK-0041, TASK-0069, TASK-0085 |
| Seguridad: SSRF, RBAC tenant-scoped, identidad de contacto, payment webhook | ✅ Producción | TASK-0077..0086 |

**Conclusión funcional y de seguridad:** **listo para go-live técnico**. No quedan brechas funcionales, ni bugs `High` abiertos, ni código legacy (TASK-0032). El runbook de go-live (TASK-0018) y la evidencia (`docs/runbook-go-live-evidence.md`) están publicados.

**Brecha que sí queda — UI:**

- `admin-panel/` tiene 26 módulos JSX (~14k LOC) pero **un único `AdminLayout` monolítico** con `if/else` por string para enrutar y **un único `global.css` de 2462 líneas** sin design system.
- **No existe UI dedicada por rol.** El panel renderiza la misma lista de módulos para Viewer / Agent / Manager / Admin / Owner / Platform Owner; los gates son `hasMinRole` repetidos 7 veces dentro de `AdminLayout.jsx`.
- **No existen** las vistas del rol **Platform Owner** (Fleet/Tenants, System Health, Billing/MRR, Incidentes, DLQ flota, Runbooks, Roles/ACL, Feature flags) — los 8 mockups en `docs/HTML DESIGN/Platform Owner/`.
- **No existen** las vistas dedicadas de **Manager** (Analítica, Campañas, Segmentos, Digest reportes), **Agente** (Inbox, Mis handoffs, Ficha de contacto, Outbound DLQ, Citas del día), ni **Viewer** (Resumen, Analítica, Citas, Conversaciones de solo lectura).
- Módulos enormes sin segregar: `OperationsDesk.jsx` (2158 LOC), `TenantSetupWizard.jsx` (2023 LOC), `ServiceCatalog.jsx` (868 LOC), `AnalyticsPanel.jsx` (786 LOC), `ContactsModule.jsx` (750 LOC), `CampaignsModule.jsx` (686 LOC).
- No hay primitivas reutilizables (Card, DataTable, Badge, Modal, FormField, EmptyState, KPI, Toast). Cada módulo replica markup y estilos.

Por eso este backlog: **levantar un design system, una capa de routing por rol y rediseñar las vistas alineadas a `HTML DESIGN/`**, sin duplicar código.

---

## 0.bis Cómo el agente extrae el diseño desde `HTML DESIGN/`

> Esta sección es **obligatoria** para toda tarea `UI-####`. Sin ella el rediseño no quedará "casi igual" al HTML.

Cada archivo en `docs/HTML DESIGN/<Rol>/<NN _ Titulo>.html` es **self-contained**: lleva la fuente embebida en base64, todo el `<style>` inline, y declara los tokens del design system en el `:root` con OKLCH + variables CSS. **El HTML es la fuente de verdad visual.** No hay Figma adicional ni guía de marca paralela; lo que está en el HTML es lo que se debe reproducir.

### 0.bis.1 — Receta de extracción para CADA pantalla

Antes de codear una vista `UI-006.x`, `UI-007.x`, `UI-008.x`, `UI-009.x` o `UI-010.x`, el agente DEBE:

1. **Abrir el HTML correspondiente** (ruta exacta en la sección 5 de este documento).
2. **Renderizarlo** con `python -m http.server` desde `docs/HTML DESIGN/` y abrir en navegador para tomar screenshot de referencia (guardar en `docs/HTML DESIGN/.screenshots/NN.png` para el PR).
3. **Extraer los tokens** del `:root` o `<style>` raíz del HTML:
   ```bash
   grep -oE '--[a-z0-9-]+ ?:[^;]+;' "docs/HTML DESIGN/<Rol>/<NN _ Titulo>.html" \
     | sort -u > /tmp/tokens-NN.css
   ```
   Estos tokens DEBEN coincidir con `src/styles/tokens.css` (UI-001). Si la pantalla declara un token que no está en `tokens.css`, **añadirlo a `tokens.css` antes de usarlo**, jamás declararlo local.
4. **Inventariar los bloques visuales** del HTML: header, sidebar, KPI grid, tabla, drawer, modal, badge, etc. Cada bloque visual recurrente que aparezca en ≥ 2 pantallas se vuelve un componente en `components/ui/` o `components/domain/`. Si ya existe, se reusa.
5. **Identificar layout/grid**: copiar valores `grid-template-columns`, `gap`, `padding` y `max-width` del contenedor principal del HTML hacia el componente React.
6. **Copiar el markup semántico** (etiquetas `<section>`, `<header>`, roles ARIA, jerarquía de `<h1>`/`<h2>`) — no inventar estructuras propias.
7. **Mapear data mock → API real**: el HTML trae datos hardcodeados. Reemplazarlos por las props/endpoints reales. La lista de endpoints está en cada subtarea.
8. **Comparar pixel-cercano** al final: screenshot del componente React lado a lado con el HTML, adjuntar al PR. Diferencias aceptables: contenido dinámico, microcopy en español; **inaceptables**: paleta distinta, radio distinto, tipografía distinta, jerarquía visual distinta.

### 0.bis.2 — Tokens raíz observados en los HTMLs (referencia inicial para UI-001)

Verificado en `Platform Owner/01 _ Fleet _ Tenants.html` (idénticos al resto de pantallas auditadas):

```css
:root {
  /* Colores */
  --bg:          #f6f5f1;
  --bg-deep:     #ecebe5;
  --panel:       #ffffff;
  --panel-alt:   #fbfaf6;
  --ink:         #0e0f0c;
  --ink-2:       #2a2b27;
  --muted:       #6b6f6a;
  --muted-2:     #9aa09a;
  --line:        #e6e4dc;
  --line-strong: #d6d3c8;

  --accent:      oklch(0.46 0.13 264);
  --accent-ink:  oklch(0.32 0.12 264);
  --accent-soft: oklch(0.94 0.03 264);
  --ok:          oklch(0.55 0.12 165);
  --ok-soft:     oklch(0.94 0.04 165);
  --warn:        oklch(0.70 0.14 70);
  --warn-soft:   oklch(0.95 0.06 75);
  --danger:      oklch(0.55 0.18 25);
  --danger-soft: oklch(0.94 0.05 25);

  /* Radios */
  --r-xs: 6px;
  --r-sm: 8px;
  --r-md: 12px;
  --r-lg: 16px;
  --r-xl: 22px;

  /* Sombras */
  --shadow-sm: 0 1px 0 rgba(14,15,12,.04), 0 1px 2px rgba(14,15,12,.04);
  --shadow-md: 0 1px 0 rgba(14,15,12,.04), 0 6px 18px -8px rgba(14,15,12,.12);

  /* Tipografía */
  --font-sans:    'Inter', ui-sans-serif, system-ui, -apple-system, sans-serif;
  --font-display: 'Inter', sans-serif;
  --font-mono:    'JetBrains Mono', ui-monospace, 'SFMono-Regular', Menlo, monospace;
}
```

**UI-001 copia este bloque tal cual** como punto de partida de `src/styles/tokens.css`. Si una pantalla específica trae tokens distintos (ej. variantes oscuras o por sección), se agregan como tokens semánticos adicionales, **nunca se sobreescriben** los base.

### 0.bis.3 — Mapping tarea ↔ archivo HTML (única fuente)

| Tarea | Archivo HTML (ruta relativa al repo) |
|---|---|
| UI-006.1 | `docs/HTML DESIGN/Platform Owner/01 _ Fleet _ Tenants.html` |
| UI-006.2 | `docs/HTML DESIGN/Platform Owner/02 _ System Health.html` |
| UI-006.3 | `docs/HTML DESIGN/Platform Owner/03 _ Billing _ MRR.html` |
| UI-006.4 | `docs/HTML DESIGN/Platform Owner/04 _ Incidentes.html` |
| UI-006.5 | `docs/HTML DESIGN/Platform Owner/05 _ Outbound DLQ _ fleet.html` |
| UI-006.6 | `docs/HTML DESIGN/Platform Owner/06 _ Runbooks.html` |
| UI-006.7 | `docs/HTML DESIGN/Platform Owner/07 _ Roles _ ACL.html` |
| UI-006.8 | `docs/HTML DESIGN/Platform Owner/08 _ Feature flags.html` |
| UI-007.1 | `docs/HTML DESIGN/OWNER : Admin/09 _ Inicio _ Dashboard.html` |
| UI-007.2 | `docs/HTML DESIGN/OWNER : Admin/10 _ Inicio _ Onboarding self-service.html` |
| UI-007.3 | `docs/HTML DESIGN/OWNER : Admin/11 _ Conversaciones _ Contactos.html` |
| UI-007.4 | `docs/HTML DESIGN/OWNER : Admin/12 _ Negocio _ Servicios.html` |
| UI-007.5 | `docs/HTML DESIGN/OWNER : Admin/13 _ Negocio _ Paquetes.html` |
| UI-007.6 | `docs/HTML DESIGN/OWNER : Admin/14 _ Negocio _ Suscripciones.html` |
| UI-007.7 | `docs/HTML DESIGN/OWNER : Admin/15 _ Negocio _ Sedes.html` |
| UI-007.8 | `docs/HTML DESIGN/OWNER : Admin/16 _ Canales _ WhatsApp Cloud API.html` |
| UI-007.9 | `docs/HTML DESIGN/OWNER : Admin/17 _ Canales _ Instagram _ Messenger.html` |
| UI-007.10 | `docs/HTML DESIGN/OWNER : Admin/18 _ IA _ Knowledge Studio.html` |
| UI-007.11 | `docs/HTML DESIGN/OWNER : Admin/19 _ IA _ Medios y promociones.html` |
| UI-007.12 | `docs/HTML DESIGN/OWNER : Admin/20 _ Config _ Tenant Setup _ Voz del bot.html` |
| UI-007.13 | `docs/HTML DESIGN/OWNER : Admin/21 _ Config _ Equipo.html` |
| UI-007.14 | `docs/HTML DESIGN/OWNER : Admin/22 _ Config _ Legal.html` |
| UI-007.15 | `docs/HTML DESIGN/OWNER : Admin/23 _ Config _ Auditoría.html` |
| UI-008.1 | `docs/HTML DESIGN/Manager/24 _ Analítica _ cómo va el negocio.html` |
| UI-008.2 | `docs/HTML DESIGN/Manager/25 _ Campañas.html` |
| UI-008.3 | `docs/HTML DESIGN/Manager/26 _ Segmentos.html` |
| UI-008.4 | `docs/HTML DESIGN/Manager/27 _ Reportes _ Digest.html` |
| UI-009.1 | `docs/HTML DESIGN/Agente/28 _ Operación _ Inbox.html` |
| UI-009.2 | `docs/HTML DESIGN/Agente/29 _ Operación _ Mis handoffs.html` |
| UI-009.3 | `docs/HTML DESIGN/Agente/30 _ Operación _ Ficha de contacto.html` |
| UI-009.4 | `docs/HTML DESIGN/Agente/31 _ Operación _ Outbound DLQ.html` |
| UI-009.5 | `docs/HTML DESIGN/Agente/32 _ Hoy _ Citas del día.html` |
| UI-010.1 | `docs/HTML DESIGN/Viewer/33 _ Lectura _ Resumen.html` |
| UI-010.2 | `docs/HTML DESIGN/Viewer/34 _ Lectura _ Analítica.html` |
| UI-010.3 | `docs/HTML DESIGN/Viewer/35 _ Lectura _ Citas.html` |
| UI-010.4 | `docs/HTML DESIGN/Viewer/36 _ Lectura _ Conversaciones.html` |

> Los nombres reales del filesystem usan guiones bajos por acentos (`Operaci_n`, `Anal_tica`, `Citas del d_a`, `Auditor_a`, `Campa_as`). La tabla los muestra con acento correcto para legibilidad; el agente abre el archivo real con `ls "docs/HTML DESIGN/<carpeta>/"` antes de leerlo.

### 0.bis.4 — Criterio de fidelidad visual (Definition of Done por vista)

Cada PR de tarea `UI-006.x`, `UI-007.x`, `UI-008.x`, `UI-009.x`, `UI-010.x` debe incluir:

1. **Screenshot del HTML de referencia** (renderizado en Chrome, viewport 1440×900).
2. **Screenshot del componente React** en el mismo viewport con datos equivalentes.
3. **Lista explícita de diferencias intencionales** (ej. "el HTML muestra 12 filas, el React pagina a 25"). Si no hay lista, se asume fidelidad 1:1.
4. **Verificación de tokens**: `grep -E "color: #|background: #|border-radius: [0-9]" src/features/<feature>/` no debe encontrar literales hardcodeados; todo viene de `var(--...)`.

---

## 1. Mandato de UI (vigente para toda tarea `UI-####`)

Este mandato extiende el de `docs/BACKLOG.md` y aplica únicamente a tareas UI:

1. **Cero duplicación.** Si dos módulos pintan una tabla, header, badge, KPI, filtro, modal o toast, **se factoriza** a `src/components/ui/<Primitive>.jsx`. Las tareas que produzcan markup repetido se rechazan.
2. **Un solo design system.** Todos los tokens (color, espaciado, tipografía, sombra, radio) viven en `src/styles/tokens.css`. Ningún módulo declara `color: #2557d6` literal; consume `var(--color-brand)`. `global.css` queda solo con resets + tipografía base.
3. **Una vista por archivo, una página por archivo.** Ningún módulo nuevo supera **400 líneas**. Si crece, se trocea en subcomponentes en su misma carpeta (`<Module>/components/`, `<Module>/hooks/`).
4. **Routing real.** Adoptar `react-router-dom` con rutas declarativas por rol y `loader`/`element`. Eliminar el `if/else` sobre `activeModuleId` en `AdminLayout.jsx`.
5. **Permisos en un solo lugar.** Crear `src/permissions/matrix.js` que codifica la matriz de la imagen `00 _ Documentación de acceso.png` (Viewer/Agent/Manager/Admin/Owner/Platform Owner). El layout, sidebar y rutas consumen esa matriz. `hasMinRole` se borra como helper ad-hoc y queda como wrapper sobre la matriz.
6. **Home por rol.** Cada rol entra a una landing distinta (Platform Owner → Fleet, Owner/Admin → Dashboard, Manager → Analítica, Agent → Inbox, Viewer → Resumen). Sin "Tenant Setup" como default para todos.
7. **Mobile-first y a11y.** Todo componente nuevo debe pasar `aria-label`/`role` mínimos y ser usable en 360px de ancho.
8. **Tests obligatorios.** Cada componente reutilizable lleva **al menos un test estático** (`@testing-library/react` + `vitest`). Cero excepciones para tareas que introducen primitivas.
9. **Sin librerías UI pesadas.** No agregar Material/Chakra/Ant. Si se necesita un dropdown accesible, se usa Radix Primitives o se construye con `<button aria-haspopup>`. Cualquier dependencia nueva se justifica en la tarea.
10. **Storybook opcional pero recomendado.** Si se agrega, una sola tarea (`UI-002.b`) lo introduce; no se mezcla con feature tasks.
11. **Romper está bien.** Mismo principio del backlog operativo: no se mantiene UI vieja en paralelo. Cuando una vista se rediseña, el componente viejo se borra.

---

## 2. Matriz roles ↔ vistas (resumen del documento de acceso)

Fuente: `docs/HTML DESIGN/00 _ Documentación de acceso.png`.

| Capacidad | Viewer | Agent | Manager | Admin | Owner | Platform Owner |
|---|---|---|---|---|---|---|
| **Operación diaria** | | | | | | |
| Ver conversaciones | R | R | R | R | R | — |
| Tomar handoff · enviar mensajes | — | R/W | R/W | R/W | R/W | — |
| Outbound DLQ · reintentar | — | R/W | R/W | R/W | R/W | — |
| Ver citas | R | R | R | R | R | — |
| Crear/editar citas | — | R/W | R/W | R/W | R/W | — |
| Ver contactos | R | R | R | R | R | — |
| Editar contacto / opt-out | — | Parcial | R/W | R/W | R/W | — |
| **Análisis y crecimiento** | | | | | | |
| Analítica de tenant | R | R | R | R | R | — |
| Rendimiento por agente | — | Solo propio | R | R | R | — |
| Segmentos | — | — | R/W | R/W | R/W | — |
| Campañas | — | — | R/W | R/W | R/W | — |
| Digest diario · suscripciones | — | — | R/W | R/W | R/W | — |
| **Configuración del negocio** | | | | | | |
| Servicios · paquetes · suscripciones | — | — | — | R/W | R/W | — |
| (Resto de filas se replican según la imagen del documento) | | | | | | |

> La matriz exhaustiva se codifica en `src/permissions/matrix.js` como dato estructurado:
> ```js
> export const PERMISSIONS = {
>   'conversations.view': { viewer: 'R', agent: 'R', manager: 'R', admin: 'R', owner: 'R', platform_owner: null },
>   'handoff.take':        { viewer: null, agent: 'RW', manager: 'RW', admin: 'RW', owner: 'RW', platform_owner: null },
>   ...
> };
> ```
> Cualquier UI que oculte/deshabilite controles consulta `hasPermission(roles, capabilityKey, mode)`.

---

## 3. Mapa de pantallas del rediseño

| Carpeta `HTML DESIGN/` | Rol primario | # Pantallas | Estado actual en `admin-panel/` |
|---|---|---|---|
| `Platform Owner/` | Platform Owner | 8 (01–08) | **No existe ninguna.** Crear módulo nuevo. |
| `OWNER : Admin/` | Owner / Admin | 15 (09–23) | Mayoría existe como módulo monolítico — rediseñar y trocear. |
| `Manager/` | Manager | 4 (24–27) | Hoy comparten Analytics/Campaigns/Segments con admin. Necesitan landing y Digest dedicada. |
| `Agente/` | Agent | 5 (28–32) | Operations Desk existe pero como monolito; faltan landing del agente, Mis handoffs, Citas del día, Ficha contacto enfocada. |
| `Viewer/` | Viewer | 4 (33–36) | **No existe.** Crear vistas read-only. |

---

## 4. Arquitectura objetivo (`admin-panel/src/`)

```
src/
├── app/
│   ├── App.jsx                       # solo provider + router
│   ├── router.jsx                    # rutas declarativas por rol (UI-003)
│   └── shells/
│       ├── PlatformOwnerShell.jsx    # layout fleet (UI-006)
│       ├── TenantShell.jsx           # layout tenant-scoped (UI-002)
│       └── ReadOnlyShell.jsx         # variante viewer (UI-010)
├── components/
│   ├── ui/                           # PRIMITIVAS (UI-001)
│   │   ├── Button.jsx
│   │   ├── Card.jsx
│   │   ├── DataTable.jsx
│   │   ├── EmptyState.jsx
│   │   ├── FormField.jsx
│   │   ├── KpiTile.jsx
│   │   ├── Modal.jsx
│   │   ├── PageHeader.jsx
│   │   ├── Pagination.jsx
│   │   ├── Sidebar.jsx
│   │   ├── StatusBadge.jsx
│   │   ├── Tabs.jsx
│   │   ├── Toast.jsx
│   │   ├── Topbar.jsx
│   │   └── index.js
│   └── domain/                       # piezas compartidas con lógica de negocio (UI-004)
│       ├── ContactCard.jsx
│       ├── ConversationListItem.jsx
│       ├── AppointmentCard.jsx
│       ├── HandoffBanner.jsx
│       └── ...
├── features/                         # una carpeta por vista
│   ├── platform/
│   │   ├── fleet-tenants/            # UI-006.1
│   │   ├── system-health/            # UI-006.2
│   │   ├── billing-mrr/              # UI-006.3
│   │   ├── incidents/                # UI-006.4
│   │   ├── fleet-dlq/                # UI-006.5
│   │   ├── runbooks/                 # UI-006.6
│   │   ├── roles-acl/                # UI-006.7
│   │   └── feature-flags/            # UI-006.8
│   ├── owner-admin/
│   │   ├── dashboard/                # UI-007.1
│   │   ├── onboarding/               # UI-007.2 (rediseño)
│   │   ├── conversations-contacts/   # UI-007.3
│   │   ├── services/                 # UI-007.4 (split de ServiceCatalog 868 LOC)
│   │   ├── packages/                 # UI-007.5
│   │   ├── subscriptions/            # UI-007.6
│   │   ├── branches/                 # UI-007.7
│   │   ├── whatsapp/                 # UI-007.8
│   │   ├── social-channels/          # UI-007.9
│   │   ├── knowledge-studio/         # UI-007.10
│   │   ├── media-library/            # UI-007.11
│   │   ├── tenant-setup/             # UI-007.12 (split de 2023 LOC)
│   │   ├── team/                     # UI-007.13
│   │   ├── legal/                    # UI-007.14
│   │   └── audit/                    # UI-007.15
│   ├── manager/
│   │   ├── analytics/                # UI-008.1
│   │   ├── campaigns/                # UI-008.2
│   │   ├── segments/                 # UI-008.3
│   │   └── digest-reports/           # UI-008.4
│   ├── agent/
│   │   ├── inbox/                    # UI-009.1
│   │   ├── my-handoffs/              # UI-009.2
│   │   ├── contact-card/             # UI-009.3
│   │   ├── outbound-dlq/             # UI-009.4
│   │   └── today-appointments/      # UI-009.5
│   └── viewer/
│       ├── summary/                  # UI-010.1
│       ├── analytics-read/           # UI-010.2
│       ├── appointments-read/        # UI-010.3
│       └── conversations-read/       # UI-010.4
├── hooks/                            # hooks compartidos
├── permissions/
│   ├── matrix.js                     # UI-005
│   └── usePermissions.js
├── services/                         # coreApi.js queda; split por dominio (UI-004.b)
└── styles/
    ├── tokens.css                    # UI-001
    ├── reset.css
    └── typography.css
```

---

## 5. Backlog de tareas UI

> Orden de ejecución: las tareas **UI-001 → UI-005 son prerequisito**. Sin design system + router + permissions, las vistas se vuelven a fragmentar.

---

### UI-001 — Design system: tokens, primitivas y migración de `global.css`

- **Estado:** DONE (tokens + primitivas + tests; `global.css` se limpia incrementalmente a medida que UI-006..UI-010 reemplacen los módulos legacy)
- **Por qué bloquea:** sin primitivas reutilizables las pantallas nuevas duplican markup y CSS. `global.css` con 2462 líneas es invertible para el equipo.
- **Fuente de los tokens:** la sección **0.bis.2** de este documento contiene el bloque exacto a copiar a `src/styles/tokens.css`. Esos valores se extrajeron de `docs/HTML DESIGN/Platform Owner/01 _ Fleet _ Tenants.html` y son consistentes con el resto de las 36 pantallas. **No inventar paleta nueva.** Si una pantalla introduce un token adicional (sombra, radio, color), se agrega aquí — no se declara local.
- **Alcance:**
  - Crear `src/styles/tokens.css` con el bloque `:root { ... }` de la sección 0.bis.2 + espaciado (`--space-1: 4px` ... `--space-8: 64px` derivados del HTML), tamaños de fuente (extraídos midiendo `font-size` del HTML por jerarquía: display, h1, h2, h3, body, small, caption) y z-index.
  - Crear `src/components/ui/` con primitivas: `Button`, `Card`, `DataTable`, `EmptyState`, `FormField`, `KpiTile`, `Modal`, `PageHeader`, `Pagination`, `StatusBadge`, `Tabs`, `Toast`. Cada primitiva en su archivo + `.module.css` (CSS Modules, no `global.css` nuevo).
  - Borrar de `global.css` todo lo que se factorizó; dejar solo reset, tipografía base y layout shell.
  - Documentar la API de cada primitiva en JSDoc.
- **Criterios de aceptación:**
  - `global.css` ≤ 400 líneas tras la limpieza.
  - Tests vitest + `@testing-library/react` ≥ 1 por primitiva (snapshot + interacción mínima).
  - `eslint src` y `vite build` pasan.
- **Dependencias:** ninguna.

---

### UI-002 — Layout shells por rol y refactor del `AdminLayout`

- **Estado:** DONE (shells por rol `TenantShell` / `PlatformOwnerShell` / `ReadOnlyShell` en `src/app/shells/`; `MfaRequiredBlocker` y `NoTenantOnboarding` migrados a `components/domain/`; `AdminLayout.jsx` eliminado por completo; `App.jsx` reducido a 15 LOC. Implementado materialmente como parte de UI-003 / UI-005; esta entrada cierra el ciclo administrativo.)
- **Por qué bloquea:** la home y la navegación deben cambiar por rol; hoy `AdminLayout.jsx` (425 LOC) es un switch monolítico.
- **Alcance:**
  - Crear `src/app/shells/TenantShell.jsx` (Topbar + Sidebar + `<Outlet/>`), `PlatformOwnerShell.jsx` (sin selector de tenant; navegación fleet), `ReadOnlyShell.jsx` (banner read-only, hide CTAs).
  - Mover `MfaRequiredBlocker` y `NoTenantOnboarding` a `src/components/domain/`.
  - El `AdminLayout` actual desaparece; `App.jsx` se reduce a `<RouterProvider router={router}/>`.
- **Criterios de aceptación:**
  - `App.jsx` ≤ 30 LOC.
  - Cada shell ≤ 200 LOC.
  - Test que un usuario `viewer` ve `ReadOnlyShell`; un `platform_owner` con `support_mode` ve `PlatformOwnerShell`.
- **Dependencias:** UI-001.

---

### UI-003 — Router declarativo con `react-router-dom` y rutas por rol

- **Estado:** DONE (`react-router-dom@6` + `app/router.jsx` con rutas por rol + `TenantProvider` + `moduleRegistry` + 10 tests; `AdminLayout`/`ModuleContent`/`useActiveModule`/`defaultModuleId` eliminados)
- **Por qué bloquea:** hoy no hay deep-link a `tenants/X/inbox/<conv_id>`; todo es estado interno. Imposible bookmarkear o compartir.
- **Alcance:**
  - Agregar `react-router-dom@6` a `admin-panel/package.json`.
  - Crear `src/app/router.jsx` con rutas:
    - `/platform/*` → `PlatformOwnerShell` (guard: `platform_owner` o `support_mode`).
    - `/t/:tenantSlug/*` → `TenantShell` con sub-rutas por feature.
    - `/t/:tenantSlug/read/*` → `ReadOnlyShell` (viewer).
    - `/login`, `/onboarding`, `/no-tenant`, `/mfa-required`.
  - Implementar `ProtectedRoute` que delega en `permissions/usePermissions`.
  - `useActiveModule` y `selectModule` quedan eliminados.
- **Criterios de aceptación:**
  - Navegar entre módulos cambia la URL.
  - Recargar la URL `/t/acme/inbox/conv_123` aterriza en la misma vista.
  - Test que un agent navegando a `/t/acme/services` recibe 403 component (no white screen).
- **Dependencias:** UI-001, UI-002, UI-005.

---

### UI-004 — Capa de componentes de dominio reutilizables

- **Estado:** DONE (`src/components/domain/`: `TagPill`, `ChannelBadge`, `PaymentBadge`, `ContactCard`, `ConversationListItem`, `AppointmentCard`, `HandoffBanner`, `TimelineEntry`, `KpiCardWithDelta` + `index.js`; 30 tests vitest; `ContactsModule` y `OperationsDesk` consumen los componentes y eliminan su markup inline duplicado. `AvatarStack` y `ServiceTile` se difieren a sus tareas de feature — no aparecen duplicados en los módulos auditados.)
- **Por qué bloquea:** `ContactsModule`, `OperationsDesk`, `CampaignsModule` repiten layout de ficha de contacto, lista de conversaciones, badges de cita.
- **Alcance:**
  - Identificar y extraer a `src/components/domain/`: `ContactCard`, `ConversationListItem`, `AppointmentCard`, `HandoffBanner`, `PaymentBadge`, `ChannelBadge`, `TagPill`, `AvatarStack`, `TimelineEntry`, `ServiceTile`, `KpiCardWithDelta`.
  - Cada componente consume primitivas de `components/ui/` (UI-001) y NO conoce de fetch — recibe data por props.
  - Borrar las copias inline de cada módulo (TenantSetupWizard, OperationsDesk, ContactsModule).
- **Criterios de aceptación:**
  - `grep -r "<div className=\"contact-card" src/` devuelve solo un archivo.
  - Reducción ≥ 15% LOC en `OperationsDesk.jsx` y `ContactsModule.jsx` antes de rediseñar.
- **Dependencias:** UI-001.

---

### UI-005 — Matriz de permisos formalizada y `usePermissions`

- **Estado:** DONE (matriz + hook + `<RequirePermission>` + refactor de `AdminLayout`; 43 tests)
- **Por qué bloquea:** la regla `hasMinRole(...)` está repetida 7 veces en `AdminLayout` y no codifica los matices del documento (`Parcial`, `Solo propio`, `R` vs `R/W`).
- **Alcance:**
  - Crear `src/permissions/matrix.js` con la matriz completa de la imagen `00 _ Documentación de acceso.png`. Una fila por **capability key** (ej. `conversations.view`, `handoff.take`, `agent.performance.read`, `services.write`, `tenants.fleet.read`, `feature_flags.write`).
  - Crear `src/permissions/usePermissions.js`: hook que recibe el contexto del tenant activo + roles y expone `can(capability, mode='R'|'RW')`.
  - Crear `<RequirePermission capability="...">` component que renderiza children, fallback (`<AccessDenied/>`) o `null`.
  - Borrar `hasMinRole`, `ROLE_LEVELS`, `PRIVILEGED_ROLES` dispersos.
  - Tests estáticos: 1 test por rol × capability crítica (≥ 40 tests).
- **Criterios de aceptación:**
  - `grep -r "ROLE_LEVELS\|hasMinRole" admin-panel/src` → 0.
  - Modificar la matriz centraliza el cambio en la UI sin tocar componentes.
  - Documentación inline en `matrix.js` referencia la imagen del documento de acceso.
- **Dependencias:** UI-001.

---

### UI-006 — Vistas del rol **Platform Owner** (8 pantallas, no existen hoy)

> Carpeta `docs/HTML DESIGN/Platform Owner/`. Cada subtarea entrega una sola feature dentro de `src/features/platform/`. Reusa `DataTable`, `KpiTile`, `PageHeader`, `StatusBadge` (UI-001).
>
> **Antes de empezar cada subtarea, aplicar la receta de 0.bis.1**: abrir el HTML mapeado en 0.bis.3, capturar screenshot de referencia, inventariar bloques visuales, y validar fidelidad al final (criterio 0.bis.4). Sin estos pasos la tarea no se considera DONE.

#### UI-006.1 — Fleet · Tenants (01) — DONE (2026-05-14)
- **Alcance:** tabla de tenants con filtros (status, país, vertical, búsqueda); columnas: tenant (avatar+slug+país), status, vertical, miembros, última actividad y owner email. KPIs agregados (tenants activos, países cubiertos) y placeholders honestos para MRR/Incidentes (UI-006.3 / UI-006.4). CTA "Nuevo tenant" → wizard de onboarding existente. Drawer con detalle del tenant y CTA "Ver como tenant" que entra al shell tenant-scoped vía `support_mode` (TASK-0077).
- **API:**
  - `POST /v1/tenants` — crear tenant. **Existe** (`platform_admin_router`, `app/api/v1/routes.py:867`; `authenticate_request` + `require_platform_owner` + `require_mfa_for_privileged`).
  - `PATCH /v1/tenants/{tenant_id}/status` — activar/suspender tenant. **Existe** (`app/api/v1/routes.py:1151`, mismas dependencias).
  - `GET /v1/tenants` — listar la flota completa con filtros (`status`, `country`, `vertical`, `search`) + paginación (`limit`, `offset`). **Implementado en UI-006.1** sobre `platform_admin_router` (`app/api/v1/routes.py:list_tenants_fleet`) con las **mismas dependencias de seguridad** que el resto del router. Cada fila incluye `member_count`, `owner_count`, `owner_email` y `last_activity_at` (este último es alias de `updated_at`; la derivación a partir de "último mensaje" llega con UI-006.2).
- **Frontend:** `src/features/platform/fleet-tenants/` (FleetTenants.jsx + componentes FleetKpis/FleetFilters/FleetTable/FleetDrawer + hook useFleetTenants). Reusa primitivas `DataTable`, `PageHeader`, `KpiTile`, `Modal`, `StatusBadge`, `EmptyState`, `Card`. `MODULE_REGISTRY['platform-fleet']` apunta a la nueva vista; el `<ModulePlaceholder>` deja de servir esta ruta.
- **Tests:** 10 backend (`tests/test_fleet_tenants_static.py`) + 5 frontend (`FleetTenants.test.jsx`: render + filtros propagados al endpoint + drawer + retry de error + AccessDenied para no-platform-owner).

#### UI-006.2 — System Health (02)
- **Alcance:** grid de KPI tiles (uptime, latencia P95 webhook inbound, latencia P95 outbound, error rate, queue depth, embedding throughput). Gráficos de series temporales (24h, 7d, 30d). Sección de incidentes activos.
- **API:** `/v1/platform/metrics/health` (consume Prometheus de TASK-0060).
- **Reusa:** `KpiTile`, `KpiCardWithDelta`, `Card`, `Tabs`.

#### UI-006.3 — Billing · MRR (03)
- **Alcance:** MRR total, MRR por plan, churn, expansión, retención. Tabla de tenants con plan, MRR, ciclo, próximo cobro, estado de cobro.
- **API:** consume datos de TASK-0075 (suscripciones) agregados a nivel plataforma.

#### UI-006.4 — Incidentes (04)
- **Alcance:** lista de incidentes con severidad, tenant afectado, status, runbook asociado. Detalle con timeline, comentarios, postmortem link.

#### UI-006.5 — Outbound DLQ · fleet (05)
- **Alcance:** vista cross-tenant del DLQ (TASK-0065). Filtros por tenant, error_code, ventana de tiempo. Reintentar masivo con confirmación.

#### UI-006.6 — Runbooks (06)
- **Alcance:** listado de runbooks (`docs/runbooks/`) con búsqueda y filtros por categoría. Cada uno se renderiza desde Markdown a HTML seguro (reusa la lógica de TASK-0076 para renderizar legal pages).

#### UI-006.7 — Roles · ACL (07)
- **Alcance:** vista read-only de la matriz `permissions/matrix.js` (UI-005) renderizada como tabla por capacidad × rol. Toggle "modo edición" solo para platform_owner que graba en `app.permission_overrides` (nueva tabla — requiere ticket backend si no existe).

#### UI-006.8 — Feature flags (08)
- **Alcance:** lista de flags con estado por tenant. Toggle inline con confirmación. Auditoría visible. (Requiere endpoint backend si no existe — confirmar con el equipo antes de cablear.)

- **Criterios globales UI-006:**
  - Cada feature ≤ 400 LOC, dividida en `index.jsx` + `components/` + `hooks/`.
  - 100% de las vistas consumen `usePermissions()` y se ocultan/deshabilitan para no-platform-owners.
  - Tests por feature: ≥ 2 (render con datos + filtro/acción crítica).
- **Dependencias:** UI-001..UI-005.

---

### UI-007 — Vistas **Owner / Admin** (15 pantallas, mayoría hoy son monolitos)

> Carpeta `docs/HTML DESIGN/OWNER : Admin/`. La estrategia es **rediseñar reusando** las primitivas y componentes de dominio. Ningún módulo nuevo > 400 LOC.
>
> **Aplica receta 0.bis.1 + mapping 0.bis.3 + criterio 0.bis.4** para cada subtarea: abrir el HTML correspondiente, screenshot de referencia, comparación lado a lado en el PR.

#### UI-007.1 — Inicio · Dashboard (09)
- **Alcance nuevo:** página de entrada para Owner/Admin con KPIs del día (citas hoy, mensajes pendientes, no-show rate semana, MRR, top servicios), alertas (handoffs sin tomar, DLQ con backlog, feedback negativo), quick links.
- **API:** ya existente (`analytics_overview`, `operations_summary`).
- **Reusa:** `KpiCardWithDelta`, `AlertBanner` (nuevo en `components/ui/`), `Card`.

#### UI-007.2 — Inicio · Onboarding self-service (10) — rediseño
- Refactor de `OnboardingWizard.jsx` (261 LOC actual): mantener lógica, aplicar nuevo stepper visual del mockup.
- Reusa `Stepper`, `FormField`, `Card`.

#### UI-007.3 — Conversaciones · Contactos (11) — split de `ContactsModule.jsx` (750 LOC)
- Trocear en: `ContactsList`, `ContactDrawer`, `ContactTimeline`, `ContactTagsPanel`, `ContactNotesPanel`. Cada uno < 200 LOC.

#### UI-007.4 — Negocio · Servicios (12) — split de `ServiceCatalog.jsx` (868 LOC)
- Trocear en: `ServicesTable`, `ServiceFormDrawer`, `ServiceReorder`, `RecallSettingsPanel`. Subcarpeta `services/components/`.

#### UI-007.5 — Negocio · Paquetes (13)
- Rediseño de `PackagesModule.jsx` siguiendo mockup; reusa `DataTable`, `Modal`.

#### UI-007.6 — Negocio · Suscripciones (14)
- Rediseño de `SubscriptionsModule.jsx`.

#### UI-007.7 — Negocio · Sedes (15)
- Rediseño de `BranchesModule.jsx` (480 LOC) — split en `BranchesList` + `BranchFormDrawer`.

#### UI-007.8 — Canales · WhatsApp Cloud API (16)
- Refactor de `WhatsAppOnboarding.jsx` (801 LOC) — split en `WhatsAppWizardSteps` + `WhatsAppHealthPanel` + `TemplatesPanel`.

#### UI-007.9 — Canales · Instagram / Messenger (17)
- Refactor de `SocialChannelsModule.jsx` reusando componentes de UI-007.8.

#### UI-007.10 — IA · Knowledge Studio (18) — refactor de 486 LOC
- Split en `DocumentsTable` + `DocumentUploader` + `DocumentDetailDrawer` + `RagSmokeTest`.

#### UI-007.11 — IA · Medios y promociones (19)
- Refactor de `MediaLibraryModule.jsx` (546 LOC) — split en `MediaGrid` + `MediaUploader` + `PromotionFormDrawer`.

#### UI-007.12 — Config · Tenant Setup · Voz del bot (20) — split crítico de `TenantSetupWizard.jsx` (2023 LOC)
- Trocear en pestañas independientes (componentes propios): `GeneralTab`, `ScheduleTab`, `BotPersonalityTab`, `EscalationTab`, `I18nTab`, `RetentionTab`, `NotificationsTab`. Cada uno ≤ 250 LOC.

#### UI-007.13 — Config · Equipo (21)
- Rediseño de `TeamModule.jsx`. Tabla con avatares, badges de rol y acciones.

#### UI-007.14 — Config · Legal (22)
- Rediseño de `LegalModule.jsx` con editor Markdown side-by-side + historial de versiones.

#### UI-007.15 — Config · Auditoría (23)
- Rediseño de `AuditPanel.jsx` con filtros densos, export CSV.

- **Criterios globales UI-007:**
  - Ningún archivo > 400 LOC.
  - Cada feature publica al menos 3 tests (render, acción crítica, gate por permiso).
  - `grep -c "className=" src/features/owner-admin/` ↓ vs estado pre-tarea (señal de extracción a primitivas).
- **Dependencias:** UI-001..UI-005.

---

### UI-008 — Vistas **Manager** (4 pantallas dedicadas)

> Carpeta `docs/HTML DESIGN/Manager/`. Hoy comparten panel con admin; la diferencia es la home + Digest.
>
> **Aplica receta 0.bis.1 + mapping 0.bis.3 + criterio 0.bis.4** para cada subtarea.

#### UI-008.1 — Analítica · cómo va el negocio (24)
- Home del manager. Reusa todos los KPIs de UI-007.1 pero con foco en conversión + funnel + rendimiento por agente. Reusa `KpiCardWithDelta`, `FunnelChart` (nuevo, en `domain/`), `AgentPerformanceTable` (extraer de `AgentPerformance.jsx`).

#### UI-008.2 — Campañas (25)
- Refactor de `CampaignsModule.jsx` (686 LOC) split en `CampaignsTable` + `CampaignFormDrawer` + `CampaignDeliveryPanel`.

#### UI-008.3 — Segmentos (26)
- Refactor de `SegmentsModule.jsx` (489 LOC) split en `SegmentsList` + `SegmentRuleBuilder` + `SegmentPreviewPanel`.

#### UI-008.4 — Reportes · Digest (27)
- **NUEVA.** Lista de digests programados (diario / semanal), suscriptores. Reusa `DigestSubscriptionsPanel.jsx` (217 LOC) y migra a `features/manager/digest-reports/`.

- **Dependencias:** UI-001..UI-005, UI-004.

---

### UI-009 — Vistas **Agente** (5 pantallas dedicadas)

> Carpeta `docs/HTML DESIGN/Agente/`. `OperationsDesk.jsx` (2158 LOC) se trocea por completo.
>
> **Aplica receta 0.bis.1 + mapping 0.bis.3 + criterio 0.bis.4** para cada subtarea.

#### UI-009.1 — Operación · Inbox (28)
- Lista de conversaciones con filtros (no asignadas, mías, con handoff, urgentes), composer integrado, panel lateral del contacto activo.
- Split de `OperationsDesk.jsx` en: `InboxList` + `ConversationView` + `MessageComposer` + `ContactSidePanel`.

#### UI-009.2 — Operación · Mis handoffs (29)
- Filtro pre-aplicado: `assignee_id = current_user`. Reusa `InboxList`.

#### UI-009.3 — Operación · Ficha de contacto (30)
- Vista enfocada del contacto (deep-link `/t/:slug/contacts/:id`). Reusa `ContactCard`, `ContactTimeline`, `AppointmentCard`.

#### UI-009.4 — Operación · Outbound DLQ (31)
- Rediseño de `OutboundDLQ.jsx` (198 LOC). Filtros y acción "Reintentar".

#### UI-009.5 — Hoy · Citas del día (32)
- Vista calendario/lista de citas del día con estados (confirmada, pendiente, no-show, completada). Reusa `AppointmentCard`, `StatusBadge`.

- **Criterios globales UI-009:**
  - Tras el refactor, ningún archivo de la antigua `OperationsDesk` queda en `modules/operations/`.
  - El agent landing por defecto es `inbox` (UI-003).
- **Dependencias:** UI-001..UI-005, UI-004.

---

### UI-010 — Vistas **Viewer** (4 pantallas read-only, no existen hoy)

> Carpeta `docs/HTML DESIGN/Viewer/`. El shell es `ReadOnlyShell` (UI-002) — banner permanente "Modo lectura", oculta CTAs.
>
> **Aplica receta 0.bis.1 + mapping 0.bis.3 + criterio 0.bis.4** para cada subtarea.

#### UI-010.1 — Lectura · Resumen (33)
- Versión read-only de UI-007.1 (dashboard). Reusa `KpiCardWithDelta`.

#### UI-010.2 — Lectura · Analítica (34)
- Reusa `AnalyticsPanel` pero envuelto en `<RequirePermission capability="analytics.read" mode="R">` y todos los export/edit CTAs ocultos.

#### UI-010.3 — Lectura · Citas (35)
- Lista paginada de citas, solo filtros y export-to-CSV opcional. Reusa `AppointmentCard`.

#### UI-010.4 — Lectura · Conversaciones (36)
- Reusa `InboxList` (UI-009.1) en modo read-only — composer oculto, CTAs handoff desactivados.

- **Criterios globales UI-010:**
  - 100% de las acciones write deben estar ocultas o renderizar `<DisabledCTA reason="read_only"/>`.
  - Test E2E: viewer abre `/t/acme/conversations` y NO encuentra ningún `<button>` write.
- **Dependencias:** UI-001..UI-005, UI-009.

---

### UI-011 — Cross-cutting: Toast, Modal global, Confirmaciones, Error boundaries

- **Estado:** PENDING
- **Alcance:**
  - `ToastProvider` global con queue (`useToast()`).
  - `ConfirmDialog` (reusa `Modal`) con API `confirm({ title, body, danger })`.
  - `<ErrorBoundary>` en cada shell con fallback amigable + report a sentry/audit.
  - Reemplazar `alert()` / `confirm()` nativos donde aparezcan.
- **Criterios:** `grep -rn "window.alert\|window.confirm" admin-panel/src` → 0.
- **Dependencias:** UI-001.

---

### UI-012 — Theming + dark mode + branding por tenant (opcional)

- **Estado:** PENDING (opcional, no bloqueante para go-live UI)
- **Alcance:** los tokens (UI-001) ya están preparados para dark mode (`@media (prefers-color-scheme: dark)`). Añadir toggle manual en topbar + persistencia local. Agregar slot de logo personalizado del tenant (lee `tenant_settings.brand_logo_url`).
- **Dependencias:** UI-001.

---

### UI-013 — Accesibilidad y responsive

- **Estado:** PENDING
- **Alcance:**
  - Auditar con `axe-core` (CI step nuevo) que cada feature pase ≥ 95 score.
  - Todas las vistas funcionales en viewport 360px.
  - Foco visible, navegación por teclado en sidebar, tablas con `role` y skip-link.
- **Criterios:** `pnpm test:a11y` (alias para axe) pasa en CI.
- **Dependencias:** UI-001 ... UI-010.

---

### UI-014 — Tests y CI

- **Estado:** PENDING
- **Alcance:**
  - Añadir `vitest` + `@testing-library/react` + `@testing-library/user-event` a `admin-panel/`.
  - Pipeline `pnpm test` corre antes del `vite build` en CI.
  - Cobertura objetivo ≥ 60% en `components/ui/` y `permissions/`, ≥ 40% en `features/`.
- **Criterios:** GitHub Actions workflow añadido o existente extendido.
- **Dependencias:** UI-001.

---

### UI-015 — Limpieza final: borrar `admin-panel/src/components/modules/`

- **Estado:** PENDING (última)
- **Alcance:**
  - Una vez todas las features migradas a `src/features/`, borrar `src/components/modules/` y `src/data/modules.js`.
  - Borrar `src/hooks/useActiveModule.js`.
  - Borrar referencias en `AdminLayout` antiguo (ya removido en UI-002).
  - `grep -rn "components/modules" admin-panel/src` → 0.
- **Dependencias:** UI-006 ... UI-010.

---

## 6. Orden recomendado de ejecución

```
UI-001 (design system)
  ↓
UI-002 (shells)  ───┐
UI-005 (permissions) ┼─→ UI-003 (router)
                    │
UI-004 (componentes de dominio) ←─┘
  ↓
UI-006.1 .. UI-006.8 (Platform Owner — nuevas pantallas)
UI-007.1 .. UI-007.15 (Owner/Admin — rediseño + split de monolitos)
UI-008.1 .. UI-008.4 (Manager)
UI-009.1 .. UI-009.5 (Agente — incluye split de OperationsDesk 2158 LOC)
UI-010.1 .. UI-010.4 (Viewer — nuevas pantallas read-only)
  ↓
UI-011 (toast/modal/error boundary)
UI-013 (a11y/responsive)
UI-014 (tests + CI)
  ↓
UI-015 (limpieza)
```

UI-012 (theming/dark mode) es opcional y puede intercalarse después de UI-001.

---

## 7. Definición de done para cualquier `UI-####`

Antes de mover una tarea a `docs/DONE.md`:

1. Todo archivo nuevo ≤ 400 LOC. Si excede, se trocea ANTES del merge.
2. Cero duplicación: cada pieza visual usada en ≥ 2 features vive en `components/ui/` o `components/domain/`.
3. Permisos visibles: cada CTA write está envuelta en `<RequirePermission>` o `usePermissions().can(...)`.
4. Tests ≥ los exigidos por la tarea.
5. `pnpm lint && pnpm build && pnpm test` en `admin-panel/` pasan en local y CI.
6. **Fidelidad visual al HTML de referencia (sección 0.bis.4):** screenshots lado a lado del HTML mapeado en 0.bis.3 y del componente React, en el mismo viewport (1440×900). Diferencias declaradas explícitamente en el PR. Sin esto el PR no se mergea.
7. **Tokens 100% extraídos del HTML:** `grep -rE "color: #|background: #[0-9a-f]|border-radius: [0-9]" src/features/<feature>/` → 0 resultados. Todo viene de `var(--...)` (sección 0.bis.2).
8. Sin código legacy: si la tarea reemplaza una vista vieja, el archivo viejo se borra en el mismo commit.

---
