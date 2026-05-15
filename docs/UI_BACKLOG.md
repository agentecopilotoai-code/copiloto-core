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

#### UI-006.2 — System Health (02) — DONE (2026-05-14)
- **Alcance:** snapshot vivo de la plataforma para Platform Owner en `/platform/platform-system-health`: grid de KPI tiles (latencia respuesta P95, mensajes procesados, outbound DLQ acumulado, worker queue depth), panel de latencia p50/p95/p99 con la alerta `BotResponseLatencyP95High` inline, tabla de estado por servicio (API, Postgres, workers, breakers de proveedores), panel de circuit breakers y lista de alertas derivadas. Respeta la referencia visual `docs/HTML DESIGN/Platform Owner/02 _ System Health.html`. **Diferencia intencional declarada:** el HTML muestra gráficos de series temporales 24h/7d/30d; la vista renderiza un snapshot puntual — las series históricas requieren la query API de Prometheus y se difieren.
- **API:** `GET /v1/platform/metrics/health` — montado en `platform_admin_router` (mismas dependencias de seguridad: `authenticate_request` + `require_platform_owner` + `require_mfa_for_privileged`). Materializa el registry Prometheus in-process de TASK-0060 (`metrics.collect_health_snapshot`) + alertas derivadas (`metrics.evaluate_health_alerts`) + un probe de conectividad de DB. Sin PII — solo agregados e IDs de proveedor/worker.
- **Frontend:** `src/features/platform/system-health/` (SystemHealth.jsx + componentes HealthKpis/HealthLatencyCard/HealthServicesTable/HealthBreakers/HealthAlerts + hook useSystemHealth). Reusa primitivas `PageHeader`, `KpiTile`, `Card`, `DataTable`, `StatusBadge`, `EmptyState`. `MODULE_REGISTRY['platform-system-health']` apunta a la nueva vista; el `<ModulePlaceholder>` deja de servir esa ruta del `PLATFORM_NAV`.
- **Tests:** 9 backend (`tests/test_system_health_static.py`: endpoint en el router correcto, no en routers de tenant, shape del snapshot, alertas derivadas, `_histogram_quantile`) + 4 frontend (`SystemHealth.test.jsx`: render con datos + alertas derivadas + retry de error + AccessDenied para no-platform-owner).

#### UI-006.3 — Billing · MRR (03) — DONE (2026-05-14)
- **Alcance:** vista de Platform Owner en `/platform/platform-billing` del ingreso recurrente del fleet: KPIs (MRR consolidado por moneda, suscripciones activas, churn 30d, cobros fallidos), tabla "Tenants por plan" (MRR por tenant + próximo cobro + estado de mora), "Composición del MRR" por plan, panel de "Cobros fallidos" agregado por tenant/proveedor y panel "Países · MRR por geografía". Respeta la referencia visual `docs/HTML DESIGN/Platform Owner/03 _ Billing _ MRR.html`. **Diferencia intencional declarada:** el HTML muestra una gráfica de evolución de MRR 12m y métricas de expansión/retención; eso requiere snapshots históricos de MRR que el schema no almacena — se difieren. La vista renderiza el snapshot puntual.
- **API:** `GET /v1/platform/billing/mrr` — montado en `platform_admin_router` (mismas dependencias de seguridad: `authenticate_request` + `require_platform_owner` + `require_mfa_for_privileged`). Agrega `app.contact_subscriptions` + `app.subscription_plans` (modelo de TASK-0075) cross-tenant: MRR mensual-normalizada por moneda/plan/tenant/país, churn 30d y cobros fallidos por (tenant, proveedor). La lectura cross-tenant pasa por `app.support_mode` (el bypass de RLS previsto por TASK-0077 para operaciones de plataforma autorizadas), seteado transaction-local. **Nota de datos:** el schema modela suscripciones tenant→contacto, no la facturación SaaS tenant→plataforma — la "MRR" aquí es el ingreso recurrente que fluye por la flota, agregado, que es exactamente lo que pide la línea de API del backlog.
- **Frontend:** `src/features/platform/billing-mrr/` (BillingMrr.jsx + componentes BillingKpis/BillingTenantsTable/MrrByPlanTable/FailedPaymentsPanel/MrrByCountryPanel + hook usePlatformBilling + format.js para helpers de moneda/porcentaje compartidos). Reusa primitivas `PageHeader`, `KpiTile`, `Card`, `DataTable`, `StatusBadge`, `EmptyState`. `MODULE_REGISTRY['platform-billing']` apunta a la nueva vista.
- **Tests:** 7 backend (`tests/test_platform_billing_static.py`: endpoint en el router correcto, no en routers de tenant, uso de support_mode + helpers, `normalize_mrr`, `fold_tenant_rows`, `summarize_mrr_by_currency`) + 4 frontend (`BillingMrr.test.jsx`: render con datos + cobros fallidos/países + retry de error + AccessDenied para no-platform-owner).

#### UI-006.4 — Incidentes (04) — DONE (2026-05-14)
- **Alcance:** vista de Platform Owner en `/platform/platform-incidents` del feed cross-tenant de incidentes: lista de incidentes con severidad derivada, tenant afectado, estado y runbook asociado; filtros por estado y tipo; KPIs (abiertos, P1, tenants afectados, notificados); drawer de detalle con el payload de la alerta y el timeline de entrega. Respeta la referencia visual `docs/HTML DESIGN/Platform Owner/04 _ Incidentes.html`. **Diferencia intencional declarada:** el HTML muestra asignación, MTTR, links de postmortem y acciones de escritura ("Marcar resuelto" / "Nuevo incidente"); eso requiere un modelo de gestión de incidentes que el schema no tiene — se difiere a un ticket de backend. Esta vista es el feed read-only.
- **API:** `GET /v1/platform/incidents` — montado en `platform_admin_router` (mismas dependencias de seguridad: `authenticate_request` + `require_platform_owner` + `require_mfa_for_privileged`). Es la vista cross-tenant de `app.operator_alerts` (TASK-0057 / TASK-0064 / TASK-0065): deriva una severidad (P1/P2/P3) y un runbook por `kind`, soporta filtros `status` y `kind`. La lectura cross-tenant pasa por `app.support_mode` — `operator_alerts` tiene RLS y un `tenant_id` nullable para alertas de sistema; el comentario del schema documenta que surfacing de filas NULL-tenant bajo `app.support_mode()` es el path de operador previsto (TASK-0064). Sin PII de contacto.
- **Frontend:** `src/features/platform/incidents/` (Incidents.jsx + componentes IncidentKpis/IncidentFilters/IncidentsTable/IncidentDrawer + hook usePlatformIncidents + meta.js para label/tone maps compartidos). Reusa primitivas `PageHeader`, `KpiTile`, `Card`, `DataTable`, `StatusBadge`, `EmptyState`, `Modal`. `MODULE_REGISTRY['platform-incidents']` apunta a la nueva vista.
- **Tests:** 7 backend (`tests/test_platform_incidents_static.py`: endpoint en el router correcto, no en routers de tenant, uso de support_mode + helpers, `severity_for_kind`/`runbook_for_kind`/`is_open`, `summarize_incidents`) + 5 frontend (`Incidents.test.jsx`: render con datos + filtro propagado + drawer con payload/timeline + retry de error + AccessDenied para no-platform-owner).

#### UI-006.5 — Outbound DLQ · fleet (05) — DONE (2026-05-14)
- **Alcance:** vista de Platform Owner en `/platform/platform-fleet-dlq` del DLQ outbound cross-tenant: KPIs (fallos en la ventana, tenants afectados, top error, códigos distintos), filtros por ventana de tiempo y error code, tabla "Por tenant" (fallos agregados + top error + acciones), panel "Distribución por error code" con runbook por código, y reintento masivo por tenant con modal de confirmación. Respeta la referencia visual `docs/HTML DESIGN/Platform Owner/05 _ Outbound DLQ _ fleet.html`. **Diferencia intencional declarada:** el tile "Auto-recuperados" del HTML se omite — la auto-recuperación no se trackea como métrica; el reintento es por tenant con confirmación explícita (no hay "reintentar todo" fleet-wide).
- **API:**
  - `GET /v1/platform/outbound-dlq` — montado en `platform_admin_router` (mismas dependencias de seguridad: `authenticate_request` + `require_platform_owner` + `require_mfa_for_privileged`). Agrega cross-tenant `app.messages` (`status=failed`, `direction=outbound`) de TASK-0065 dentro de la ventana, agrupado por tenant y error code. Filtros `window_minutes`, `tenant_id`, `error_code`. La lectura cross-tenant pasa por `app.support_mode` (RLS en `app.messages`), seteada transaction-local. El query nunca selecciona cuerpos de mensaje ni identificadores de contacto — solo conteos.
  - `POST /v1/platform/outbound-dlq/retry` — reintento masivo del DLQ de **un** tenant (sin "reintentar todo" fleet-wide). Cada mensaje se re-encola por el mismo path `requeue_message` que un reintento manual individual, así que las garantías de idempotencia y domain-events son idénticas. La acción se audita (`platform.outbound_dlq.bulk_retried`).
- **Frontend:** `src/features/platform/fleet-dlq/` (FleetDlq.jsx + componentes DlqKpis/DlqFilters/DlqByTenantTable/DlqByErrorCodePanel/DlqRetryConfirm + hook usePlatformDlq). Reusa primitivas `PageHeader`, `KpiTile`, `Card`, `DataTable`, `Modal`, `EmptyState` y `<RequirePermission>`. `MODULE_REGISTRY['platform-fleet-dlq']` apunta a la nueva vista.
- **Tests:** 8 backend (`tests/test_platform_dlq_static.py`: ambos endpoints en el router correcto, no en routers de tenant, uso de support_mode + audit, export de `requeue_tenant_dlq`, `fold_dlq_by_tenant`/`summarize_by_error_code`/`summarize_fleet_dlq`/`runbook_for_error_code`) + 5 frontend (`FleetDlq.test.jsx`: render con datos + filtro de ventana propagado + reintento masivo vía modal de confirmación + error state + AccessDenied para no-platform-owner).

#### UI-006.6 — Runbooks (06) — DONE (2026-05-14)
- **Alcance:** vista de Platform Owner en `/platform/platform-runbooks` del catálogo de runbooks operacionales de `docs/runbooks/`: grid de tarjetas con título/categoría/tamaño, búsqueda por título/slug y filtro por categoría (ambos client-side, el catálogo es pequeño), y visor modal que renderiza el Markdown a HTML seguro. Respeta la referencia visual del panel "Runbooks disponibles" de `docs/HTML DESIGN/Platform Owner/04 _ Incidentes.html`.
- **API:**
  - `GET /v1/platform/runbooks` — montado en `platform_admin_router` (mismas dependencias de seguridad: `authenticate_request` + `require_platform_owner` + `require_mfa_for_privileged`). Lista los `.md` de `docs/runbooks/` (README excluido) con slug/filename/título/categoría/tamaño.
  - `GET /v1/platform/runbooks/{slug}` — devuelve un runbook renderizado a HTML seguro vía `render_markdown_to_safe_html` (TASK-0076) — el mismo subconjunto de Markdown totalmente escapado que usan las páginas legales públicas. Defensa de path-traversal: el slug se valida contra `^[a-z0-9][a-z0-9-]*$` y la ruta resuelta se verifica dentro de `docs/runbooks/` antes de cualquier lectura.
- **Frontend:** `src/features/platform/runbooks/` (Runbooks.jsx + componentes RunbookFilters/RunbookList/RunbookViewer + hooks useRunbooks/useRunbookDetail). Reusa primitivas `PageHeader`, `Card`, `StatusBadge`, `EmptyState`, `Modal` y `<RequirePermission>`. El visor usa `dangerouslySetInnerHTML` sobre el HTML server-sanitizado. `MODULE_REGISTRY['platform-runbooks']` apunta a la nueva vista.
- **Tests:** 9 backend (`tests/test_platform_runbooks_static.py`: ambos endpoints en el router correcto, no en routers de tenant, render vía `render_markdown_to_safe_html`, validación de slug + path-traversal, `categorize_runbook`/`extract_title`, listado de los archivos reales sin README, `read_runbook`) + 5 frontend (`Runbooks.test.jsx`: render del catálogo + filtro por categoría + filtro por búsqueda + visor con HTML renderizado + AccessDenied para no-platform-owner).

#### UI-006.7 — Roles · ACL (07) — DONE (2026-05-14)
- **Alcance:** vista read-only de Platform Owner en `/platform/platform-roles-acl` de la matriz `permissions/matrix.js` (UI-005) renderizada como tabla por capacidad × rol, agrupada por dominio (Operación diaria, Análisis y crecimiento, Configuración del negocio, Canales e IA, Administración del tenant, Platform Owner · fleet), con búsqueda client-side de capacidades, tiles de conteo de capacidades por rol, leyenda de niveles de acceso y panel estático "Política de roles". **Tarea frontend-only** — no toca el backend; la matriz ya existe en `src/permissions/matrix.js`. **Diferencia intencional declarada:** (1) el HTML mockup `07 _ Roles _ ACL.html` muestra *asignaciones de rol por usuario* (usuarios × tenants × MFA), que requeriría un endpoint cross-tenant de usuarios; el backlog (esta tarea) pide la matriz capacidad × rol de `permissions/matrix.js` hecha visible — eso es lo que renderiza la vista, reusando el styling del HTML. (2) El toggle "modo edición" que grabaría en `app.permission_overrides` se difiere: esa tabla no existe y es un ticket de backend aparte (el backlog ya lo marca como tal).
- **API:** ninguna — la vista consume directamente `PERMISSIONS` / `ROLES` de `src/permissions/matrix.js`. El gate de visibilidad usa `<RequirePermission capability="platform.roles_acl.read" mode="R">`.
- **Frontend:** `src/features/platform/roles-acl/` (RolesAcl.jsx + componentes RolesAclMatrix/RolesAclFilters/AccessPolicyPanel + helper puro rolesAclData.js). Reusa primitivas `PageHeader`, `KpiTile`, `Card`, `DataTable`, `StatusBadge`, `EmptyState` y `<RequirePermission>`. `MODULE_REGISTRY['platform-roles-acl']` apunta a la nueva vista.
- **Tests:** 8 frontend (`rolesAclData.test.js`: `categorizeCapability`, `buildMatrixGroups` cubre toda la matriz y filtra por búsqueda, `countCapabilitiesPerRole`; `RolesAcl.test.jsx`: render de la matriz agrupada + panel de política + filtro de búsqueda + tiles por rol + AccessDenied para no-platform-owner).

#### UI-006.8 — Feature flags (08) — DONE (2026-05-14)
- **Alcance:** vista read-only de Platform Owner en `/platform/platform-feature-flags` del catálogo de feature flags del producto: KPIs (total, default On, conteo por tipo), búsqueda por key/descripción y filtro por tipo (client-side), y tabla con key + descripción, estado default, rollout % informativo, tipo y la TASK de origen. Respeta el styling del HTML de referencia `08 _ Feature flags.html`. **Decisión de alcance:** el backlog marca esta tarea como "Requiere endpoint backend si no existe — confirmar con el equipo antes de cablear", y no existe ningún sistema de feature flags en el backend (sin tabla de schema, sin motor de rollout, sin store de overrides). En vez de construir un subsistema escribible completo sin confirmación del equipo, se entrega el **catálogo read-only honesto**: un registro estático (`app/services/feature_flags.py`) de los flags reales del producto, cada uno mapeado a su TASK de origen — mismo patrón que `platform_runbooks` (catálogo estático servido read-only, sin DB). **Diferencia intencional declarada:** el HTML muestra toggles en vivo, sliders de rollout gradual y overrides por tenant; eso requiere el sistema escribible persistido y auditado que se difiere al ticket de backend.
- **API:** `GET /v1/platform/feature-flags` — montado en `platform_admin_router` (mismas dependencias de seguridad: `authenticate_request` + `require_platform_owner` + `require_mfa_for_privileged`). Read-only, sin DB: sirve el registro estático de `app/services/feature_flags.py` + un resumen. **No hay handler POST/PATCH/PUT/DELETE** para feature flags — un test estático lo verifica como contrato (el sistema escribible está diferido).
- **Frontend:** `src/features/platform/feature-flags/` (FeatureFlags.jsx + componentes FeatureFlagKpis/FeatureFlagFilters/FeatureFlagsTable + hook useFeatureFlags + meta.js para label/tone maps compartidos). Reusa primitivas `PageHeader`, `KpiTile`, `Card`, `DataTable`, `StatusBadge`, `EmptyState` y `<RequirePermission>`. `MODULE_REGISTRY['platform-feature-flags']` apunta a la nueva vista.
- **Tests:** 6 backend (`tests/test_feature_flags_static.py`: endpoint en el router correcto, no en routers de tenant, **read-only verificado** — sin verbos de escritura, registro bien formado, `list_feature_flags` devuelve copias, `summarize_feature_flags`) + 5 frontend (`FeatureFlags.test.jsx`: render del catálogo + filtro por tipo + filtro por búsqueda + retry de error + AccessDenied para no-platform-owner).

- **UI-006 completo:** las 8 subtareas (UI-006.1..UI-006.8) están `DONE`. El rol Platform Owner tiene sus 8 vistas implementadas.

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

#### UI-007.1 — Inicio · Dashboard (09) — DONE (2026-05-14)
- **Alcance:** página de entrada Owner/Admin en `/t/:slug/dashboard`: saludo contextual + KPIs con variación semana-a-semana (citas confirmadas, no-show rate, conversaciones abiertas, mensajes recibidos, ingresos estimados), sección de alertas operativas derivadas de la analítica (handoffs pendientes, feedback negativo, no-show alto) y grid de accesos rápidos. Es ahora el **home de los roles Owner y Admin** (`ROLE_HOME.owner`/`admin` → `dashboard`; Manager sigue en `analytics`). Respeta el styling del HTML `09 _ Inicio _ Dashboard.html`. **Diferencia intencional declarada:** el HTML muestra además una lista de "citas de hoy", un funnel a 7 días y un panel de canales; esta vista se enfoca en el alcance de UI-007.1 (KPIs + alertas + quick links) — funnel y citas tienen sus vistas dedicadas enlazadas desde los accesos rápidos. La "MRR" / "top servicios" del backlog se mapean honestamente a "Ingresos estimados" (lo que `analytics_overview` provee); no se fabrican datos no modelados.
- **API:** `GET /v1/analytics/overview` — endpoint **ya existente** (`tenant_analytics_router`, sin cambios de backend). El dashboard lo consume dos veces (ventana actual 7d + previa 7d) para los deltas de `KpiCardWithDelta`.
- **Frontend:** nueva primitiva `components/ui/AlertBanner.jsx` (+ css + test) exportada en `components/ui/index.js`; `src/features/owner-admin/dashboard/` (Dashboard.jsx + componentes DashboardKpis/DashboardAlerts/DashboardQuickLinks + hook useDashboardData + helper puro dashboardData.js). Reusa `KpiCardWithDelta`, `AlertBanner`, `Card`, `PageHeader`, `EmptyState`, `<RequirePermission>`. Wiring: `dashboard` en `data/modules.js` + `moduleRegistry.js` + `nav.js` (sección "Inicio"); `matrix.js` `ROLE_HOME` owner/admin → `dashboard`.
- **Tests:** 12 frontend — `AlertBanner.test.jsx` (3), `dashboardData.test.js` (5), `Dashboard.test.jsx` (4). Actualizados `router.test.jsx` y `usePermissions.test.jsx` por el nuevo `ROLE_HOME`.

#### UI-007.2 — Inicio · Onboarding self-service (10) — DONE (2026-05-14)
- **Alcance:** rediseño del `OnboardingWizard.jsx` legacy (261 LOC) — se mantiene íntegra la lógica de TASK-0069 (wizard de 7 pasos con verificación server-side: `verify`/`complete`/test E2E del bot) y se aplica el stepper visual del mockup. Migrado a `src/features/owner-admin/onboarding/`; el archivo legacy `components/modules/onboarding/OnboardingWizard.jsx` se borró en el mismo commit. **Tarea frontend-only** — no toca el backend; los endpoints de onboarding ya existían.
- **Frontend:** nueva primitiva `components/ui/Stepper.jsx` (+ css + test) exportada en `components/ui/index.js` — stepper vertical con marcadores de estado, línea conectora y slots `badge`/`children` por paso. `src/features/owner-admin/onboarding/` (Onboarding.jsx + componente OnboardingStep + helper puro onboardingSteps.js). Reusa `Stepper`, `FormField`, `Card`, `PageHeader`, `StatusBadge`, `AlertBanner`, `EmptyState`, `<RequirePermission>`. Wiring: `moduleRegistry.js` `'onboarding-wizard'` → `Onboarding` (mismo id de módulo, misma capability `onboarding.run` mode RW).
- **Tests:** 10 frontend — `Stepper.test.jsx` (4), `onboardingSteps.test.js` (3), `Onboarding.test.jsx` (3: render + progreso + 7 pasos, verificación server-side, AccessDenied para rol sin `onboarding.run`).

#### UI-007.3 — Conversaciones · Contactos (11) — DONE (2026-05-14)
- **Alcance:** split del monolito `ContactsModule.jsx` (685 LOC) en `src/features/owner-admin/conversations-contacts/`: orquestador `ConversationsContacts.jsx` (91 LOC) + hook `useContactsData` (214 LOC, toda la lógica CRM) + helper puro `contactsFormat.js` + 6 componentes presentacionales — `ContactsList`, `ContactDrawer`, `ContactTagsPanel`, `ContactPackagesPanel`, `ContactTimeline` (citas + conversaciones + referidos + consentimiento), `ContactNotesPanel` — todos < 200 LOC. **Tarea frontend-only** — la lógica se preserva verbatim del módulo legacy; los endpoints CRM ya existían. El archivo legacy `components/modules/contacts/ContactsModule.jsx` se borró en el mismo commit. Reusa primitivas `Card`/`FormField`/`StatusBadge`/`EmptyState`/`AlertBanner`/`PageHeader` y domain `ContactCard`/`AppointmentCard`/`TagPill`/`TimelineEntry`. Migrado de clases de `global.css` a CSS module con tokens 100% `var(--...)`.
- **Tests:** 9 frontend (`contactsFormat.test.js` ×5; `ConversationsContacts.test.jsx` ×4: render de lista + auto-carga del primer contacto, selección de contacto, búsqueda propagada, AccessDenied). Actualizados 6 tests estáticos de backend (`test_crm_contacts_static`, `test_packages_static`, `test_consent_ledger_static`, `test_referrer_tracking_static`, `test_qualification_flow_static`, `test_contact_package_authz`) para apuntar al feature dir nuevo vía lectura combinada — los `data-testid` (`contact-packages-panel`/`contact-consent-panel`/`contact-referrals-panel`) se preservaron en los componentes nuevos.

#### UI-007.4 — Negocio · Servicios (12) — DONE (2026-05-14)
- **Alcance:** split del monolito `ServiceCatalog.jsx` (868 LOC) en `src/features/owner-admin/services/`: orquestador `Services.jsx` + hook `useServicesData` (estado del catálogo + mutaciones) + helper puro `servicesData.js` + componentes en `components/` — `ServicesTable`, `ServiceReorder`, `ServiceFormDrawer` (que compone `RecallSettingsPanel` TASK-0052 y `AppliesWhenBuilder` TASK-0054) y `DefaultDurationPanel`. **Tarea frontend-only** — la lógica se preserva verbatim; los endpoints ya existían. El archivo legacy se borró en el mismo commit. La tabla está gateada por `services.read`; el form de creación/edición y el panel de duración por defecto son superficies de escritura gateadas por `<RequirePermission capability="services.write" mode="RW" hidden>` (el backend sigue siendo la autoridad). Migrado a CSS module con tokens 100% `var(--...)`.
- **Tests:** 13 frontend (`servicesData.test.js` ×8: formatos, `normalizeRuleValue`/`rulesToPayload`/`rulesFromService` roundtrip, `buildPayload` recall, `buildPreview`, `formFromService`; `Services.test.jsx` ×5: render tabla + form para owner, modo edición, reorden, form oculto para rol read-only, AccessDenied). Actualizados 5 tests estáticos de backend (`test_service_catalog_static`, `test_media_promotions_static`, `test_service_applies_when_static`, `test_service_recall_static`, `test_booking_flow_static`) para apuntar al feature dir nuevo vía lectura combinada; los `data-testid` de `applies-when-builder`/`applies-when-rule` se preservaron.

#### UI-007.5 — Negocio · Paquetes (13) — DONE (2026-05-14)
- **Alcance:** rediseño de `PackagesModule.jsx` (346 LOC) en `src/features/owner-admin/packages/`: orquestador `Packages.jsx` + hook `usePackagesData` (estado del catálogo + modal/form + mutaciones) + helper puro `packagesData.js` + componentes `PackagesTable` (reusa `DataTable`) y `PackageFormModal` (reusa `Modal`). **Tarea frontend-only** — la lógica se preserva verbatim; los endpoints ya existían. El catálogo pasó de lista a `DataTable`; el form de alta/edición pasó de inline a `Modal`. El archivo legacy se borró en el mismo commit. Gateado por `<RequirePermission capability="packages.write" mode="RW">`. CSS module con tokens 100% `var(--...)`.
- **Tests:** 10 frontend (`packagesData.test.js` ×6: `emptyForm`/`toForm`/`buildPayload` válido+inválido/`describeServices`/`formatPrice`; `Packages.test.jsx` ×4: render tabla activos+inactivos, modal de creación, modal de edición pre-cargado, AccessDenied). Actualizado `test_packages_static.py` para apuntar al feature dir nuevo vía lectura combinada + verificar que la ruta legacy ya no está en el registry.

#### UI-007.6 — Negocio · Suscripciones (14) — DONE (2026-05-14)
- **Alcance:** rediseño de `SubscriptionsModule.jsx` (366 LOC) en `src/features/owner-admin/subscriptions/`: orquestador `Subscriptions.jsx` + hook `useSubscriptionsData` (estado de planes/suscriptores + modal/form + tab + mutaciones) + helper puro `subscriptionsData.js` + componentes `SubscriptionsKpis` (grid de `KpiTile`), `PlansPanel` (lista de planes con badge de estado), `SubscribersTable` (`Tabs` + `DataTable`) y `PlanFormModal` (reusa `Modal`). **Tarea frontend-only** — la lógica de mutación se preserva verbatim; los endpoints ya existían. El form de alta/edición pasó de inline a `Modal`; la lista de suscriptores pasó a `DataTable` con tabs Todos/Activos/Past-due/Cancelados. El archivo legacy se borró en el mismo commit. Gateado por `<RequirePermission capability="subscriptions.write" mode="RW">`. CSS module con tokens 100% `var(--...)`. **Diferencia intencional declarada:** el HTML muestra un KPI "Churn 30d" — no hay snapshot de churn modelado, así que ese tile se reemplaza honestamente por "Cancelados" (derivable) y el MRR se deriva de los suscriptores activos × precio del plan normalizado a mes; no se fabrican datos.
- **Tests:** 13 frontend (`subscriptionsData.test.js` ×8: `emptyPlanForm`/`toPlanForm`/`buildPlanPayload` válido+inválido/`monthlyAmount`/`computeKpis`/`filterSubscribers`/labels; `Subscriptions.test.jsx` ×5: render KPIs+planes+tabla, modal de creación, modal de edición pre-cargado, filtro por tab past-due, AccessDenied). Actualizado `test_subscriptions_static.py` para apuntar al feature dir nuevo vía lectura combinada + verificar que la ruta legacy ya no está en el registry.

#### UI-007.7 — Negocio · Sedes (15) — DONE (2026-05-14)
- **Alcance:** rediseño de `BranchesModule.jsx` (480 LOC) en `src/features/owner-admin/branches/`: vista `BranchesManager` (PageHeader + lista + drawer, **ungated** a propósito) + orquestador `Branches.jsx` (`<RequirePermission capability="branches.write" mode="RW">` envolviendo a `BranchesManager`) + hook `useBranchesData` (estado de sedes + drawer/form + helpers de franjas horarias + mutaciones) + helper puro `branchesData.js` + componentes `BranchesList` (grid de cards), `BranchFormDrawer` (reusa `Modal`) y `OpeningHoursEditor` (editor de franjas por día, < 70 LOC). **Tarea frontend-only** — la lógica se preserva verbatim (incluido `buildMapsUrlFromInputs`, espejo de `app/services/maps.py` de TASK-0058); los endpoints ya existían. El form de alta/edición pasó de inline a `Modal`; la lista pasó de `<ul>` a grid de cards. El archivo legacy se borró en el mismo commit. **`BranchesManager` se exporta sin gate** porque el `TenantSetupWizard` lo embebe en su pestaña "Sedes" igual que reusaba el módulo legacy — una sola implementación, dos puntos de entrada (registry gateado vs. wizard directo). CSS module con tokens 100% `var(--...)`. **Diferencia intencional declarada:** el HTML muestra mini-stats por sede (Equipo, Citas 30d, Ocupación), un panel de mapa y un bar chart "Citas por sede" — esos agregados dependen de joins de `resources`/`appointments` que el endpoint `/branches` no expone; se difieren y la card muestra los datos reales del endpoint (horario derivado, zona horaria, código). No se fabrican datos.
- **Tests:** 13 frontend (`branchesData.test.js` ×8: `emptyForm`/`toForm`/`buildPayload` válido+inválido/`buildMapsUrlFromInputs` coords+address+null/`summarizeHours`/`formatLocation`; `Branches.test.jsx` ×5: render de cards con badge Principal + resumen de horario, drawer de creación con editor de horarios, drawer de edición pre-cargado, AccessDenied para rol sin `branches.write`, render del manager para rol con permiso). Actualizados `test_branches_static.py` y `test_maps_static.py` para apuntar al feature dir nuevo vía lectura combinada + verificar el import nuevo en registry y wizard.

#### UI-007.8 — Canales · WhatsApp Cloud API (16) — DONE (2026-05-14)
- **Alcance:** refactor de `WhatsAppOnboarding.jsx` (801 LOC) en `src/features/owner-admin/whatsapp/`: orquestador `WhatsAppOnboarding.jsx` (`<RequirePermission capability="whatsapp.read">` + tabs WhatsApp/Widget Web) + hook `useWhatsAppData` (canal/health/templates + mutaciones) + helper puro `whatsappData.js` + los tres componentes del split: `WhatsAppWizardSteps` (form de canal + checklist `Stepper`), `WhatsAppHealthPanel` (snapshot de salud + identificadores) y `TemplatesPanel` (semáforo de requeridas + form de alta + `DataTable`). **Tarea frontend-only** — la lógica (upsert de canal, refresh de health con manejo de 404, CRUD/sync de plantillas) se preserva verbatim; los endpoints ya existían. El archivo legacy se borró en el mismo commit. `WebWidgetPanel.jsx` **no** es parte de este rediseño (es otro canal sin tarea UI propia): se queda en `components/modules/whatsapp/` y el orquestador nuevo lo importa desde ahí. CSS module con tokens 100% `var(--...)`. **Diferencia intencional declarada:** el HTML muestra KPIs de volumen 24 h (mensajes enviados, tasa de entrega/lectura, fallos outbound, ventana 24 h) y un feed de últimas entregas del webhook — `getWhatsAppChannelHealth` no expone esos datos; se difieren y el panel muestra los checks reales del endpoint. No se fabrican datos.
- **Tests:** 12 frontend (`whatsappData.test.js` ×8: `emptyTemplateForm`/`defaultFormForTenant`, `formFromChannel` sin secretos, `templateComponentsFromForm`, `validateTemplateForm`, `hasValue`/`channelFromHealth`, `groupTemplatesByPurpose`, `buildChecklist`, `buildRequiredSemaphore`; `WhatsAppOnboarding.test.jsx` ×4: render de wizard+health+templates, switch a tab Widget Web, alta de plantilla vía form, AccessDenied para rol sin `whatsapp.read`). Actualizados `test_whatsapp_delivery_static.py`, `test_whatsapp_templates_static.py` y `test_web_widget_static.py` para apuntar al feature dir nuevo vía lectura combinada.

#### UI-007.9 — Canales · Instagram / Messenger (17) — DONE (2026-05-14)
- **Alcance:** refactor de `SocialChannelsModule.jsx` (265 LOC) en `src/features/owner-admin/social-channels/`: orquestador `SocialChannelsModule.jsx` (`<RequirePermission capability="social_channels.write" mode="RW">` + tabs de proveedor Instagram DM / Facebook Messenger) + hook `useSocialChannelsData` (lista de canales + provider activo + form upsert + mutación) + helper puro `socialChannelsData.js` + componentes `SocialChannelStatus` (panel de identificadores Meta + checks de secretos) y `SocialChannelForm` (form de alta/edición reusando `Card`+`FormField`). Reusa las mismas primitivas que el rediseño WhatsApp de UI-007.8. **Tarea frontend-only** — la lógica (upsert del canal, ordenamiento de canales, validación HMAC/ventana 24 h server-side) se preserva verbatim; los endpoints ya existían. El archivo legacy se borró en el mismo commit. CSS module con tokens 100% `var(--...)`. **Diferencia intencional declarada:** el HTML muestra KPIs de tráfico 24 h (DMs entrantes, respuestas bot, fuera de ventana, handoffs, citas, conversión), la lista de eventos suscritos del webhook y un feed de mensajes recientes — `listMessengerChannels` no expone esos datos; se difieren y el panel muestra los identificadores + checks reales del endpoint. No se fabrican datos.
- **Tests:** 10 frontend (`socialChannelsData.test.js` ×6: `emptyForm`, `providerMeta`, `channelForProvider`, `statusLabel`/`statusTone`, `channelRecipientId`, `buildPayload` válido+inválido; `SocialChannelsModule.test.jsx` ×4: render de ambos tabs + status + form, switch a tab Facebook Messenger, submit del upsert, AccessDenied para rol sin `social_channels.write`). Actualizado `test_meta_messenger_static.py` para apuntar al feature dir nuevo vía lectura combinada.

#### UI-007.10 — IA · Knowledge Studio (18) — DONE (2026-05-14)
- **Alcance:** refactor de `KnowledgeStudio.jsx` (486 LOC) en `src/features/owner-admin/knowledge-studio/`: orquestador `KnowledgeStudio.jsx` (`<RequirePermission capability="knowledge.read">` + PageHeader con CTAs «Test RAG» / «Subir documento» + banner `local_hash`) + hook `useKnowledgeStudioData` (documentos + filtros + form editor + form upload + estado del RAG tester + todas las mutaciones) + helper puro `knowledgeStudioData.js` + el split de cuatro componentes: `DocumentsTable` (reusa `DataTable` + filtros estado/visibilidad + acciones por fila), `DocumentUploader` (`Modal` de carga de archivos), `DocumentDetailDrawer` (`Modal` de alta/edición de documento) y `RagSmokeTest` (`Modal` que consume `POST /v1/intents/evaluate` y muestra intención + respuesta + chunks). **Tarea frontend-only** — la lógica (CRUD de documentos, indexado, cambio de estado, carga de archivos con extracción en background, evaluación RAG) se preserva verbatim; los endpoints ya existían. El archivo legacy se borró en el mismo commit. La lista pasó de `<aside>` a `DataTable`; los formularios inline pasaron a `Modal`. CSS module con tokens 100% `var(--...)`. **Diferencia intencional declarada:** el HTML muestra una card «Storage» (backend/bucket/tamaño) — eso pertenece al módulo separado `knowledge-storage` (UI ya existente) y no se duplica aquí.
- **Tests:** 11 frontend (`knowledgeStudioData.test.js` ×6: `formFromDocument`, `buildPayload`, `embeddingProviderBadge`, `extractionStatusBadge`/`isAwaitingExtraction`, `documentSummary`, `hasLocalHashActive`; `KnowledgeStudio.test.jsx` ×5: render de la tabla con documentos, apertura del drawer de subida, apertura del drawer de creación, apertura del RAG tester + evaluación de una pregunta, AccessDenied para rol sin `knowledge.read`). No hay tests estáticos de backend que apuntaran al módulo legacy.

#### UI-007.11 — IA · Medios y promociones (19) — DONE (2026-05-14)
- **Alcance:** refactor de `MediaLibraryModule.jsx` (546 LOC) en `src/features/owner-admin/media-library/`: orquestador `MediaLibraryModule.jsx` (`<RequirePermission capability="media.write" mode="RW">` + PageHeader con CTAs «Nueva promoción» / «Subir medio») + hook `useMediaLibraryData` (assets + promociones + servicios + form upload + form promo + todas las mutaciones) + helper puro `mediaLibraryData.js` + el split: `MediaGrid` (grid de assets con búsqueda client-side por etiqueta/tag), `MediaUploader` (`Modal` de carga con inferencia de tipo + validación de tamaño), `PromotionFormDrawer` (`Modal` de alta/edición de promoción) y `PromotionsList` (lista de promociones). **Tarea frontend-only** — la lógica (CRUD de medios y promociones, inferencia de `kind` por mime, límites de tamaño por tipo, parseo de tags) se preserva verbatim; los endpoints ya existían. El archivo legacy se borró en el mismo commit. Los formularios inline pasaron a `Modal`; el grid y la lista pasaron de markup con estilos inline a primitivas + CSS module con tokens 100% `var(--...)`. **Diferencia intencional declarada:** el HTML muestra una card «Resumen del bucket» (nº de archivos, tamaño total, envíos 30 d, más usado) y un contador «usos» por asset — los endpoints de medios no exponen esos agregados; se difieren. No se fabrican datos.
- **Tests:** 12 frontend (`mediaLibraryData.test.js` ×7: `inferKindFromFile`, `validateUploadFile`, `labelFromFileName`, `promoFormFromPromotion`, `parseTags`, `buildPromoPayload` válido+inválido, `formatBytes`; `MediaLibraryModule.test.jsx` ×5: render de grid + lista de promociones, apertura del uploader, apertura del drawer de promoción, filtro de búsqueda del grid, AccessDenied para rol sin `media.write`). Actualizado `test_media_promotions_static.py` para apuntar al feature dir nuevo vía lectura combinada.

#### UI-007.12 — Config · Tenant Setup · Voz del bot (20) — split crítico de `TenantSetupWizard.jsx` (2023 LOC) — DONE (2026-05-14)
- **Alcance:** split estructural puro de `TenantSetupWizard.jsx` (2023 LOC) en `src/features/owner-admin/tenant-setup/`: orquestador `TenantSetupWizard.jsx` (shell `module-card wizard-card` + nav `.tabs` + render de la pestaña activa; sin gate porque la entrada del registry `tenant-setup` tiene `capability: null`) + hooks `useTenantSetupData` (estado del tenant/settings + carga + `handleSaveTenant`/`handleSaveSettings`/`handleChangeStatus`/`handleProviderChange`/`handleReindexAll`/`refreshAuditLogs`) y `useTenantSetupSidePanels` (etiquetas de contacto + pagos + retención, extraído para mantener cada hook ≤ 400 LOC) + datos puros `tenantSetupData.js` + transforms puros `tenantSetupTransforms.js` + 13 componentes de pestaña (`GeneralTab`, `QualificationTab`, `SettingsTab`, `ScheduleTab`, `BranchesTab`, `EscalationTab`, `IntentsTab`, `NotificationsTab` + `ComplaintAlertChannelsFieldset` extraído, `PaymentsTab`, `PrivacyTab`, `BotPersonalityTab`, `RagTab`, `AuditTab`) + `QualificationQuestionsPanel` y `DigestSubscriptionsPanel` movidos a `components/`. **Refactor frontend-only** — markup, classNames, estilos inline, atributos `data-*` y lógica preservados verbatim; sin rediseño visual, sin CSS module (se conservan las clases globales de `global.css`). Cada archivo creado ≤ 400 LOC. El directorio legacy `components/modules/tenantSetup/` se borró en el mismo commit; `moduleRegistry.js` y `router.jsx` repuntados al feature dir.
- **Tests:** 14 frontend (`tenantSetupTransforms.test.js` ×10: `hydrateBotPersonality`, `renderPersonalityPreview`, `hydrateNotificationSettings`, `hydrateIntentSettings`, `toBusinessHours`, `toEscalationPolicy`, `toPiiPolicy`, `slugifyVertical`; `TenantSetupWizard.test.jsx` ×4: render del heading + nav completa de pestañas, pestaña General por defecto, switch a «Horarios», switch a «Voz del bot»). ~18 tests estáticos de backend repuntados al feature dir vía lectura combinada (`_tenant_setup_source()`); 2 aserciones ajustadas a la nueva estructura (ruta de import de `BranchesManager` y la indentación del `<select>` de país), preservando su intención.

#### UI-007.13 — Config · Equipo (21) — DONE (2026-05-14)
- **Alcance:** rediseño de `TeamModule.jsx` (325 LOC) en `src/features/owner-admin/team/`: orquestador `TeamModule.jsx` (`<RequirePermission capability="team.write" mode="RW">` + PageHeader con CTA «Invitar miembro» + banner Auth0 + tiles de conteo por rol) + hook `useTeamData` (miembros + flag Auth0 + form de invitación + mutaciones) + helper puro `teamData.js` + `TeamTable` (reusa `DataTable`: avatar + nombre/email + badge de rol + select de rol + estado + revocar, con buscador client-side) y `InviteMemberForm` (`Modal`). **Tarea frontend-only** — la lógica (invitación vía Auth0, cambio de rol, revocación, guards de owner: solo un owner asigna/edita owner, no se puede revocar al último owner) se preserva verbatim; los endpoints ya existían. El archivo legacy se borró en el mismo commit. La tabla pasó de `<table>` cruda a `DataTable`; el form de invitación de inline a `Modal`. CSS module con tokens 100% `var(--...)`. **Diferencia intencional declarada:** el HTML muestra una columna «MFA» por miembro y un badge «N sin MFA» en el header — `listTenantMembers` no expone el estado de MFA; se difiere. No se fabrican datos.
- **Tests:** 9 frontend (`teamData.test.js` ×5: `emptyInviteForm`, `highestRole`, `memberInitials`, `callerIsOwner`, `roleCounts`; `TeamModule.test.jsx` ×4: render de tiles + tabla, apertura del drawer de invitación, filtro de búsqueda, AccessDenied para rol sin `team.write`). Actualizados `test_tenant_team_static.py` y `test_auth0_invite.py` para apuntar al feature dir nuevo vía lectura combinada (los literales `Invitar miembro`, `Auth0 Management API no está habilitada`, `recibirá un email de Auth0`, ausencia de `ticket_url`/`pendingTicket` se preservaron).

#### UI-007.14 — Config · Legal (22) — DONE (2026-05-14)
- **Alcance:** rediseño de `LegalModule.jsx` (356 LOC) en `src/features/owner-admin/legal/`: orquestador `LegalModule.jsx` (`<RequirePermission capability="legal.write" mode="RW">` + PageHeader + `AlertBanner` para error/info) + hook `useLegalData` (documentos + form de borrador + agrupación por kind + mutaciones) + helper puro `legalData.js` + el split de tres componentes: `PublishedDocuments` (versión publicada vigente por kind + URL pública), `MarkdownEditor` (editor side-by-side Markdown + preview sanitizada) y `VersionHistory` (historial append-only por kind con `DataTable` + acción Publicar). **Tarea frontend-only** — la lógica (creación de borrador, publicación, el renderer de subset Markdown seguro con `escapeHtml`/`renderInline`/`renderPreview`) se preserva verbatim; los endpoints ya existían. El archivo legacy se borró en el mismo commit. Las tablas de historial pasaron de `<table>` cruda a `DataTable`; el preview sigue usando `dangerouslySetInnerHTML` solo sobre HTML escapado por el renderer. CSS module con tokens 100% `var(--...)`.
- **Tests:** 9 frontend (`legalData.test.js` ×6: `emptyDraft`, `escapeHtml`, `renderInline` (escapa + rechaza `javascript:`), `renderPreview`, `groupByKind`/`publishedByKind`, `docStatusLabel`/`docStatusTone`; `LegalModule.test.jsx` ×3: render de los tres paneles, preview en vivo al escribir Markdown, AccessDenied para rol sin `legal.write`). Actualizado `test_legal_documents_static.py` para apuntar al feature dir nuevo vía lectura combinada (los literales `function escapeHtml`, `function renderPreview`, `dangerouslySetInnerHTML`, `https?:\/\/`, `mailto:` se preservaron).

#### UI-007.15 — Config · Auditoría (23) — DONE (2026-05-14)
- **Alcance:** rediseño de `AuditPanel.jsx` (255 LOC) en `src/features/owner-admin/audit/`: orquestador `AuditPanel.jsx` (`<RequirePermission capability="audit.read">` + PageHeader + `AlertBanner`) + hook `useAuditData` (query de logs + filtros densos + supresión de contacto + export de datos del tenant) + helper puro `auditData.js` + el split de tres componentes: `AuditFilters` (form denso de filtros + export CSV), `AuditTable` (reusa `DataTable` para los logs) y `PrivacyTools` (supresión GDPR + export de datos + resumen DPA). **Tarea frontend-only** — la lógica (query filtrada, export CSV, export de datos del tenant, supresión irreversible de contacto con `window.confirm`) se preserva verbatim; los endpoints ya existían. El archivo legacy se borró en el mismo commit. Las tablas pasaron de `<table>` cruda a `DataTable`; los formularios reusan `FormField`. CSS module con tokens 100% `var(--...)`. **Diferencia intencional declarada:** el HTML muestra un sidebar de conteos por categoría y columnas «Cambio» / «IP/SDK» por fila — `listAuditLogsFiltered` no expone esos datos; se difieren. La tabla muestra los campos reales del endpoint. No se fabrican datos.
- **Tests:** 9 frontend (`auditData.test.js` ×5: `emptyFilters`, `buildFilterPayload` con/sin límite, `formatDate`, `ACTOR_TYPE_OPTIONS`/`DPA_POLICY`; `AuditPanel.test.jsx` ×4: render de filtros + privacy tools + DPA, query de logs → tabla, export CSV con filtros, AccessDenied para rol sin `audit.read`). Actualizado `test_audit_privacy_static.py` para apuntar al feature dir nuevo vía lectura combinada (los literales `audit-table`, `handleSuppressContact`, `handleExportTenantData`, `danger-action`, `confirm`, `no_train`, `DPA`, `listAuditLogsFiltered`/`exportAuditLogs`/`exportTenantData`/`suppressContact` se preservaron).

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

#### UI-008.1 — Analítica · cómo va el negocio (24) — DONE (2026-05-14)
- **Alcance:** home dedicada del Manager en `src/features/manager/analytics/` (orquestador `ManagerAnalytics.jsx` + `hooks/useManagerAnalyticsData.js` + `managerAnalyticsData.js` puro + `components/{ManagerKpis,ConversionFunnel,AgentPerformanceTable,CampaignsSummary}.jsx` + `.module.css` + `index.js`). Nuevo componente de dominio `FunnelChart` en `components/domain/`. `AgentPerformanceTable` extraída como componente presentacional feature-local desde el markup + lógica de orden del legacy `AgentPerformance.jsx` (el legacy queda intacto: sigue usado por el `AnalyticsPanel` de Owner/Admin). Routing: nuevo module id `manager-analytics` (registry + `data/modules.js` + `nav.js` sección Inicio) y `ROLE_HOME.manager` repuntado de `analytics` a `manager-analytics`. Reusa `KpiCardWithDelta`. **Diferencia intencional declarada:** el HTML muestra una gráfica de ingreso diario apilado por canal, KPIs "Ingreso atribuido" y "CAC por canal", y una lista "Top servicios"; ninguno está expuesto por los endpoints de analítica — se difieren, no se fabrican datos. Los KPIs renderizados (ingreso estimado, citas asistidas, retención 90d, tasa de no-show) usan campos reales de `analytics_overview`.
- **Tests:** `managerAnalyticsData.test.js` (6 — formatters, `sortAgents`, `buildManagerKpis`, `buildFunnelSegments`, `buildCampaignRows`), `ManagerAnalytics.test.jsx` (4 — render + fetch de los 4 endpoints, KPIs/tabla/funnel, resumen de campañas, `AccessDenied` sin `analytics.tenant.read`), `FunnelChart.test.jsx` (3 — render de segmentos, empty state, aria-label).

#### UI-008.2 — Campañas (25) — DONE (2026-05-14)
- **Alcance:** refactor de `CampaignsModule.jsx` (686 LOC) en `src/features/manager/campaigns/`: orquestador `CampaignsModule.jsx` (`<RequirePermission capability="campaigns.write" mode="RW">` + `PageHeader` con CTA «Nueva campaña» + `AlertBanner` para notices) + hook `useCampaignsData` (lista de campañas + selección + lookups de templates/etiquetas/segmentos guardados + form de creación/edición + estado de preview, con los handlers `refreshCampaigns`/`submit`/`preview`/`launch`/`cancel` portados verbatim, incluidos los `window.confirm` nativos de lanzar/cancelar) + helper puro `campaignsData.js` (catálogo de estados + tonos, `EMPTY_FILTER`, `emptyCampaignForm`, `formFromCampaign`, `buildPayload` con validación, `parseVariables`/`serializeVariables`, `formatDate`, `buildDeliveryMetrics`) + el split de tres componentes: `CampaignsTable` (reusa `DataTable` — estado, segmento, métricas, acciones por fila editar/destinatarios/programar/cancelar gateadas por estado), `CampaignFormDrawer` (`Modal` con el form: nombre, template aprobado, variables, fecha de envío, picker de `Segmento guardado` vía `listContactSegments` + filtros de segmento alternativos) y `CampaignDeliveryPanel` (resumen + barras de métricas de entrega + preview de destinatarios estimados). **Tarea frontend-only** — toda la lógica, las llamadas a `coreApi` y las reglas de negocio se preservan verbatim; los endpoints ya existían. El archivo legacy se borró en el mismo commit. La lista pasó de un sidebar `conversation-card` a `DataTable`; el form de inline a `Modal`; las barras de progreso de estilos inline a CSS module con tokens 100% `var(--...)`. `moduleRegistry.js` repuntado al feature dir (el id `campaigns` y el nombre `CampaignsModule` no cambian).
- **Tests:** 10 frontend (`campaignsData.test.js` ×6: `statusLabel`/`statusTone`, round-trip `parseVariables`/`serializeVariables`, `buildPayload` válido, `buildPayload` rechazo + preferencia de `segment_id`, `formFromCampaign`, `deliveryPercent`/`buildDeliveryMetrics`; `CampaignsModule.test.jsx` ×4: render de la tabla para un manager, apertura del drawer de creación, render del picker de segmento guardado, `AccessDenied` para rol sin `campaigns.write`). Repuntados `test_campaigns_static.py` y `test_segments_static.py` al feature dir nuevo vía lectura combinada (`_campaigns_feature_source()`); los literales `export function CampaignsModule`, `listCampaigns`, `createCampaign`, `previewCampaign`, `launchCampaign`, `listContactSegments`, `segment_id`, `Segmento guardado` se preservaron en los archivos nuevos.

#### UI-008.3 — Segmentos (26) — DONE (2026-05-14)
- **Alcance:** refactor de `SegmentsModule.jsx` (489 LOC) en `src/features/manager/segments/`: orquestador `SegmentsModule.jsx` (`<RequirePermission capability="segments.write" mode="RW">` + `PageHeader` con CTA «Nuevo segmento» + `AlertBanner` para notices) + hook `useSegmentsData` (lista de segmentos + selección + form de creación/edición con el array dinámico de reglas + estado de preview, con los handlers `refreshSegments`/`submit`/`preview`/`refresh`/`remove` y los del rule-builder portados verbatim, incluido el `window.confirm` nativo de borrado) + helper puro `segmentsData.js` (catálogo de tipos + tonos, catálogos de campos/operadores del rule-builder, `emptySegmentForm`, `formFromSegment`, `buildPayload` con validación, las funciones puras add/replace/remove/update de reglas, `rulesToConditions`/`conditionsToRules`, `formatDate`) + el split mandado de tres componentes: `SegmentsList` (reusa `DataTable` — tipo vía `StatusBadge`, contactos, refrescado, acciones por fila editar/previsualizar/refrescar/eliminar gateadas igual que el legacy), `SegmentRuleBuilder` (constructor dinámico de reglas: combinador AND/OR + filas campo+operador+valor con añadir/quitar) compuesto dentro de `SegmentFormDrawer` (`Modal` de creación/edición: nombre, descripción, tipo) y `SegmentPreviewPanel` (resumen del segmento + muestra en vivo vía `previewContactSegment`). **Tarea frontend-only** — toda la lógica, las llamadas a `coreApi` y las reglas de negocio se preservan verbatim; los endpoints ya existían. El archivo legacy se borró en el mismo commit. La lista pasó de un sidebar `conversation-card` a `DataTable`; el form de inline a `Modal`; los estilos inline a CSS module con tokens 100% `var(--...)`. `moduleRegistry.js` repuntado al feature dir (el id `segments` y el nombre `SegmentsModule` no cambian). Sin diferencias intencionales declaradas: todos los campos del HTML que los endpoints exponen se renderizan.
- **Tests:** 11 frontend (`segmentsData.test.js` ×7: `fieldKind`/`operatorsForField`, `updateRuleField`/`updateRuleValue` con casteo numérico, `parseListValue`, add/replace/remove inmutables, round-trip `rulesToConditions`/`conditionsToRules`, `buildPayload` válido + rechazo de nombre vacío, `formFromSegment`; `SegmentsModule.test.jsx` ×4: render de la lista para un manager, apertura del drawer de creación, render del rule-builder dinámico, `AccessDenied` para rol sin `segments.write`). Repuntado `test_segments_static.py` al feature dir nuevo vía lectura combinada (`_segments_feature_source()`); los literales `export function SegmentsModule`, `listContactSegments`, `previewContactSegment`, `refreshContactSegment` se preservaron en los archivos nuevos.

#### UI-008.4 — Reportes · Digest (27) — DONE (2026-05-14)
- **Alcance:** nueva vista del Manager en `src/features/manager/digest-reports/` (orquestador `DigestReports.jsx` con `<RequirePermission capability="digest.write" mode="RW">` + `PageHeader` + hook `useDigestReportsData.js` + helper puro `digestReportsData.js` + `components/{DigestSubscribersSummary,DigestSubscriptionsPanel}.jsx` + `.module.css` + `index.js`). El `DigestSubscriptionsPanel.jsx` (217 LOC) se **relocó verbatim** desde `features/owner-admin/tenant-setup/components/` — toda la lógica, las 4 llamadas a `coreApi` (`listDigestSubscriptions`/`createDigestSubscription`/`updateDigestSubscription`/`deleteDigestSubscription`), las reglas de negocio (validación «al menos un email o whatsapp», `window.confirm` de borrado, opciones de cadencia, toggle) y los `data-*` (`data-wizard-field`, `data-digest-form`, `data-digest-row`) se preservaron; solo se corrigió el path de import de `coreApi` y se cambiaron los classNames/estilos inline legacy por el CSS module con tokens 100% `var(--...)`. Sigue siendo `default export`: el `NotificationsTab` del wizard tenant-setup lo embebe desde su nueva ruta. Routing: nuevo module id `digest-reports` (registry + `data/modules.js` + `nav.js` sección Conversaciones). **Diferencia intencional declarada:** el HTML muestra un botón «Enviar ahora» y un panel rico de «Preview · digest diario» con KPIs — ninguno tiene endpoint backing (los únicos endpoints de digest son los 4 CRUD de suscripciones) — se difieren, no se fabrican datos.
- **Tests:** 8 frontend (`digestReportsData.test.js` ×5: `CADENCE_OPTIONS`/`emptyForm`, `cadenceLabel`, `recipientLabel`/`recipientInitials`, `formatLastSent`, `summarizeSubscriptions`; `DigestReports.test.jsx` ×4: render del panel + tabla de suscriptores para un manager, render del form «Suscribir destinatario», validación «al menos un email o whatsapp», `AccessDenied` para rol sin `digest.write`). Repuntado `test_digest_static.py`: helper `_digest_reports_source()` nuevo + `test_wizard_renders_digest_subscriptions_panel` ahora verifica el import-line a la nueva ruta y lee el panel relocado para el loop de nombres `coreApi`.

- **Dependencias:** UI-001..UI-005, UI-004.

---

### UI-009 — Vistas **Agente** (5 pantallas dedicadas)

> Carpeta `docs/HTML DESIGN/Agente/`. `OperationsDesk.jsx` (2158 LOC) se trocea por completo.
>
> **Aplica receta 0.bis.1 + mapping 0.bis.3 + criterio 0.bis.4** para cada subtarea.

#### UI-009.1 — Operación · Inbox (28) — DONE (2026-05-14)
- **Alcance:** split estructural del monolito `OperationsDesk.jsx` (2088 LOC) a la feature `src/features/agente/inbox/` — orquestador `OperationsDesk.jsx` (`export function OperationsDesk`, gateado con `<RequirePermission capability="conversations.view">`) + `inboxData.js` puro + 4 hooks (`useInboxData` lista/filtros/stream SSE/composer/handoff, `useContactPanelData` etiquetas+notas, `useScheduleData` recursos/agenda/citas/pagos, `useServiceRequestsData` SR+cotizaciones) + componentes `InboxList` + `ConversationView` + `MessageComposer` + `ContactSidePanel` (este último compuesto por `contact-panel/{ContactTagsSection,ContactScheduleSection,ContactResourceForm,ContactServiceRequestsSection}`) + `MessageContent`. Toda la lógica se preserva verbatim: ~38 llamadas a `coreApi`, el stream WebSocket con reconexión backoff exponencial, la máquina de estados de handoff, el append optimista del detalle y todos los `data-*`. El id de módulo sigue siendo `operations-desk` por estabilidad de routing (la carpeta es `inbox/`); el home del agente `operations-desk` ahora renderiza este Inbox, satisfaciendo «el landing del agente es inbox». Todos los archivos ≤ 400 LOC.
- **Tests:** `inboxData.test.js` (10 tests de helpers puros) + `OperationsDesk.test.jsx` (5 tests: render del inbox para un agente, apertura del stream WebSocket, detalle de conversación al seleccionar, cambio de filtro Quejas, `AccessDenied` sin `conversations.view`). 13 tests estáticos de pytest repuntados al feature dir vía un helper `_operations_desk_source()` que concatena el `*.js*` de la carpeta.

#### UI-009.2 — Operación · Mis handoffs (29) — DONE (2026-05-14)
- **Alcance:** nueva vista del rol Agente en `src/features/agente/my-handoffs/` que reutiliza la maquinaria del Inbox con un filtro de handoffs pre-aplicado. Se ampliaron los exports del barrel `agente/inbox/index.js` (`InboxList`, `useInboxData`) sin tocar su comportamiento. `useMyHandoffsData` es un wrapper fino sobre `useInboxData` — NO re-consulta nada: corre sobre la misma respuesta tenant-scoped de `listConversations` y filtra en cliente por `active_handoff_assigned_to = current_user` (el `app.users.id` que el backend graba al aceptar un handoff; el id del agente se resuelve desde `profile.sub`). Encima añade sólo la resolución del usuario actual + el estado de la tab de filtro (`Todos` / `Sin asignar` / `Mías`) + la lista derivada y los conteos. `MyHandoffsList` reutiliza el componente de dominio `ConversationListItem` (el mismo que usa `InboxList`) — `InboxList` no se reusa tal cual porque su API está acoplada al form «iniciar conversación» y a las tabs `Todas` / `Quejas`. Las acciones de handoff (`acceptHandoff` / `releaseHandoff`) se reusan verbatim del Inbox. El orquestador `MyHandoffs.jsx` está gateado con `<RequirePermission capability="conversations.view" mode="R">`. Nuevo módulo `my-handoffs` cableado en `moduleRegistry.js` / `data/modules.js` / `nav.js` (sección Conversaciones, junto a `operations-desk`); `ROLE_HOME` no se tocó. Todos los archivos ≤ 400 LOC.
- **Diferencias intencionales declaradas:** el HTML muestra KPIs ("Esperando humano", "Asignadas a mí", "Resueltas hoy", "% por bot · semana", "tiempo medio mío", "cerca de SLA") y columnas de SLA por fila que `listConversations` no expone — se difieren (no se inventan datos). Las tabs `Colegas` / `Cerrados` tampoco tienen respaldo en el endpoint y se difieren. Se renderiza sólo lo que la respuesta de conversaciones realmente trae (cliente, estado, tiempo de espera derivado de `handoff_created_at` / `updated_at`, y la acción «Tomar» / liberar vía la acción de handoff existente del Inbox).
- **Tests:** `myHandoffsData.test.js` (7 tests de helpers puros: definición de tabs, detección de handoff, filtro completo / por usuario actual / sin asignar, `applyHandoffFilter` + `deriveHandoffCounts`, `toHandoffRow`) + `MyHandoffs.test.jsx` (5 tests: render de la cola excluyendo conversaciones bot-only, cambio a tab «Mías», cambio a tab «Sin asignar», seleccionar + aceptar un handoff sin asignar vía la acción del Inbox, `AccessDenied` sin `conversations.view`).

#### UI-009.3 — Operación · Ficha de contacto (30) — DONE (2026-05-14)
- **Alcance:** nueva vista enfocada del contacto en `src/features/agente/contact-profile/`, accesible vía el deep-link `/t/:tenantSlug/contacts/:contactId`. Es una ruta (no un módulo, no aparece en la nav) añadida como hermana de `...TENANT_MODULE_IDS.map(moduleRoute)` dentro del subárbol `TenantShellRoute` de `router.jsx`; `contacts/:contactId` es más profunda que el módulo `contacts` exacto, así que no colisiona. Sólo se cableó en el shell principal (no en el subárbol `read` de Viewer): el rol objetivo es el Agente, que usa ese shell; el Viewer es redirigido fuera del shell principal y el deep-link es una herramienta operativa. El orquestador `ContactProfile.jsx` resuelve `activeTenant` desde `useOutletContext()`, `contactId`/`tenantSlug` desde `useParams()` y `{ profile, session }` desde `useTenantContext()` — no recibe props. Gateado con `<RequirePermission capability="contacts.view" mode="R">` (por eso no se envuelve en `<ModuleScreen>`). `useContactProfileData` lee en paralelo `getContactProfile` + `listContactConsent` (este último tolera fallo con `.catch(() => null)`), con estados loading/error/not-found; vista de sólo lectura, sin handlers de mutación. Reutiliza el componente de dominio `ContactCard` (fila de identidad canónica), `AppointmentCard` y `TimelineEntry` (vía el `ContactTimeline` reusado), y el panel `ContactTimeline` de la feature `conversations-contacts` — cuyo barrel se amplió (`ContactTimeline`, `formatDate`, `formatDateShort`, `renderQualificationAnswer`) sin tocar comportamiento. Los helpers puros propios viven en `contactProfileData.js` (identidad/iniciales, KPIs de resumen, etiqueta de consentimiento). Todos los archivos ≤ 400 LOC (el mayor no-test es `ContactProfile.jsx`, 115 LOC).
- **Diferencias intencionales declaradas:** el HTML muestra KPIs "LTV", "NPS", "No-shows", "Referidos" como métricas, y campos "Cumpleaños", "Sede preferida", "Canal preferido", "Próxima cita", paneles "Productos activos" / "Sin suscripciones activas" y un buscador `⌘K` — ninguno está expuesto por `getContactProfile` ni `listContactConsent`, así que se difieren (no se inventan datos). Se renderiza sólo lo que las dos respuestas realmente traen: identidad del contacto, etiquetas, `stats` (citas totales/completadas/calificación), conteo de notas, estado de consentimiento, y el historial de citas/conversaciones/referidos/consentimiento del `ContactTimeline`.
- **Tests:** `contactProfileData.test.js` (5 tests de helpers puros: `contactDisplayName`, `contactInitials`, `summaryStats` con y sin `stats`, `notesCount` + `consentStatusLabel`) + `ContactProfile.test.jsx` (4 tests: render de la ficha enfocada desde el param del deep-link, estado "Contacto no encontrado" cuando `getContactProfile` devuelve nada, estado de error cuando rechaza, `AccessDenied` para un rol sin `contacts.view`). `router.test.jsx` mantiene exactamente los 7 fallos de entorno documentados (Node-24 `undici`/`AbortSignal`), sin nuevas regresiones por la ruta añadida.

#### UI-009.4 — Operación · Outbound DLQ (31) — DONE (2026-05-14)
- **Alcance:** rediseño de `OutboundDLQ.jsx` (198 LOC) en `src/features/agente/outbound-dlq/`: orquestador `OutboundDLQ.jsx` (`<RequirePermission capability="outbound_dlq.retry" mode="RW">` + PageHeader + `AlertBanner`) + hook `useOutboundDlqData` (lista de fallidos + totales por error code + filtro activo + selección de detalle + retry) + helper puro `outboundDlqData.js` (catálogo de labels de error de Meta, formatters) + el split de tres componentes: `DlqErrorChips` (chips de filtro por error code), `DlqTable` (reusa `DataTable`) y `DlqDetailModal` (reusa `Modal`). **Tarea frontend-only** — la lógica (fetch con filtro, retry con `window.confirm` + acción auditada `outbound.dlq.retried` server-side) se preserva verbatim; los endpoints ya existían. El archivo legacy se borró en el mismo commit. El modal ad-hoc pasó a `Modal`, la tabla cruda a `DataTable`; los `data-error-code` / `data-action="retry"` / `data-module="outbound-dlq"` se preservaron. CSS module con tokens 100% `var(--...)`.
- **Tests:** 8 frontend (`outboundDlqData.test.js` ×4: `errorCodeLabel` (conocidos + fallback), `formatDate`, `shortId`, `totalFailures`; `OutboundDLQ.test.jsx` ×4: render de chips + tabla, retry vía acción de fila, apertura del modal de detalle, AccessDenied para rol sin `outbound_dlq.retry`). Actualizado `test_outbound_dlq_static.py` para apuntar al feature dir nuevo vía lectura combinada + el import nuevo en el registry.

#### UI-009.5 — Hoy · Citas del día (32) — DONE (2026-05-14)
- **Alcance:** nueva vista del rol Agente en `src/features/agente/today-appointments/`: lista de las citas del día con su estado en vivo (confirmada, sin confirmar, atendida, no-show), reutilizando los componentes de dominio `AppointmentCard` (que a su vez reusa `StatusBadge`) y el mapa de tonos `appointmentStatusTone`. El orquestador `TodayAppointments.jsx` (`<RequirePermission capability="appointments.view" mode="R">` + `PageHeader` + navegador de día Día anterior / Hoy / Mañana) compone `DayAppointmentsSummary` (KPIs derivables) + `TodayAppointmentsList` (filas `AppointmentCard` ordenadas por hora, con `EmptyState`). El hook `useTodayAppointmentsData` posee el día seleccionado (por defecto hoy), trae la lista completa vía `listAppointments` (tenant-scoped server-side) y aplica el **filtro por día en cliente** sobre el campo real `starts_at` — `listAppointments` no expone un parámetro de fecha establecido en el frontend (ver `useScheduleData`, que lo llama sin filtros), así que no se inventa uno. Helpers puros en `todayAppointmentsData.js` (`todayISO`/`dateKey`/`shiftDayISO`, `filterByDay`, `sortByTime`, `deriveCounts`, `nextAppointment`, `groupByStatus`, formatters, mapas de estado). El módulo `appointments` —que estaba en `VIEWER_NAV` pero sin entrada en `moduleRegistry.js` ni `data/modules.js`, renderizando como `ModulePlaceholder`— quedó cableado: `moduleRegistry.js` (`appointments → TodayAppointments`, capability `appointments.view`), `data/modules.js` (entrada nueva) y `nav.js` (nueva sección «Hoy» en `TENANT_NAV` para agentes/managers; `ROLE_HOME` no se tocó). Todos los archivos ≤ 400 LOC (el mayor, `todayAppointmentsData.js`, 152 LOC).
- **Diferencias intencionales declaradas:** el HTML muestra una grilla «Agenda» recurso × franja horaria, KPIs de «Ocupación %» e «Ingreso proyectado» y un CTA «Nueva cita» — `listAppointments` devuelve registros planos y no expone carriles de agenda por recurso, ocupación ni monto proyectado del día, y la creación de citas vive en el panel de contacto del Inbox; todo eso se difiere (no se inventan datos ni se cablea un botón a la nada). Se renderiza la **lista** de citas (el entregable núcleo del backlog: «calendario/lista … Reusa AppointmentCard, StatusBadge») + los conteos derivables (total del día, sin confirmar, atendidas, próxima cita) + la navegación de día.
- **Tests:** 10 frontend (`todayAppointmentsData.test.js` ×6: `dateKey`/`shiftDayISO`/`todayISO`, `filterByDay`, `sortByTime`, `deriveCounts`, `nextAppointment`, `groupByStatus`+`statusLabel`+`statusTone`; `TodayAppointments.test.jsx` ×4: render de la lista del día + tiles de resumen, navegación a «Mañana» re-filtra la lista, «Hoy» la devuelve al día actual, `AccessDenied` para un rol sin `appointments.view`). `router.test.jsx` mantiene exactamente los 7 fallos de entorno documentados (Node-24 `undici`/`AbortSignal`); registrar el módulo `appointments` no introdujo regresiones (el test mockea `moduleRegistry.js` por completo).

- **Criterios globales UI-009:**
  - Tras el refactor, ningún archivo de la antigua `OperationsDesk` queda en `modules/operations/`.
  - El agent landing por defecto es `inbox` (UI-003).
- **Dependencias:** UI-001..UI-005, UI-004.

---

### UI-010 — Vistas **Viewer** (4 pantallas read-only, no existen hoy)

> Carpeta `docs/HTML DESIGN/Viewer/`. El shell es `ReadOnlyShell` (UI-002) — banner permanente "Modo lectura", oculta CTAs.
>
> **Aplica receta 0.bis.1 + mapping 0.bis.3 + criterio 0.bis.4** para cada subtarea.

#### UI-010.1 — Lectura · Resumen (33) — DONE (2026-05-14)
- **Alcance:** nueva vista read-only del rol Viewer en `src/features/viewer/summary/`, aplicando el mockup `33 _ Lectura _ Resumen.html`. Es la versión Viewer del dashboard (UI-007.1) y **reusa la maquinaria del dashboard**: `useDashboardData` (mismo hook que el Owner/Admin — dos llamados a `getAnalyticsOverview` ventana actual + previa, NO se refetchea) y `DashboardKpis` (que a su vez reusa `KpiCardWithDelta` del dominio). El barrel del dashboard `features/owner-admin/dashboard/index.js` se amplió con esos dos exports nombrados para evitar deep-imports — sin cambios de comportamiento en el dashboard original. El orquestador `ViewerSummary.jsx` gatea con `<RequirePermission capability="analytics.tenant.read" mode="R">` + `PageHeader` («Resumen del negocio» + chip de período "Últimos 7 días · <mes> <año>") + estados loading/error/empty + `<DashboardKpis>` reusado. Helpers puros en `summaryData.js` (`periodLabel`, `SUMMARY_DESCRIPTION`, re-exports de `buildKpis`/`formatMoney` del dashboard). El hook `useSummaryData` es un wrapper fino sobre `useDashboardData` que añade el `periodLabel` derivado y el flag `readOnly: true`. **No se renderiza `DashboardQuickLinks` ni `DashboardAlerts`** — ambos exponen botones de navegación / CTAs que el criterio global UI-010 exige ocultar; el `ReadOnlyShell` (UI-002) ya pone el banner permanente "Modo solo lectura". El nuevo módulo `viewer-summary` se cableó en `moduleRegistry.js` (capability `analytics.tenant.read`), `data/modules.js`, `app/nav.js` (encabeza la sección «Lectura» de `VIEWER_NAV`) y `permissions/matrix.js` (`ROLE_HOME.viewer` cambió de `'analytics'` a `'viewer-summary'`). `router.jsx` se ajustó para que los fallbacks del subárbol Viewer (`/t/:slug/read` index + `ReadOnlyShellRoute`) usen `ROLE_HOME.viewer` en vez del literal `'analytics'`. Todos los archivos ≤ 400 LOC (el mayor, `ViewerSummary.jsx`, 92 LOC).
- **Diferencias intencionales declaradas:** el HTML muestra (a) una gráfica «Ingreso mensual · últimos 12 meses», (b) un breakdown «Mix de servicios» por categoría y (c) un breakdown «Origen de pacientes» por canal. `analytics_overview` (única fuente que alimenta el dashboard) no expone series de 12 meses ni porcentajes por servicio/origen, así que los tres bloques se difieren — no se inventan datos. Se renderiza el entregable mínimo viable del backlog («Versión read-only de UI-007.1. Reusa `KpiCardWithDelta`.»): título + chip de período + las KPIs reusadas del dashboard.
- **Tests:** 9 frontend (`summaryData.test.js` ×5: `periodLabel` (formato es-CO, cobertura enero/diciembre, fallback sin argumento), `SUMMARY_DESCRIPTION` menciona ventana semanal + cadencia de 15 minutos, re-exports `buildKpis`/`formatMoney` del dashboard; `ViewerSummary.test.jsx` ×4: render del PageHeader + chip de período + grid `aria-label="Indicadores del negocio"` con las KPIs reusadas, NO se renderiza «Accesos rápidos» / «Alertas» / botones de acción del Owner Dashboard, EmptyState defensivo cuando el tenant aún no expone `id`, `AccessDenied` para un rol sin `analytics.tenant.read`). Se añadió un test a `matrix.test.js` que pinea `ROLE_HOME.viewer === 'viewer-summary'`. `router.test.jsx` mantiene exactamente los 7 fallos de entorno documentados (Node-24 `undici`/`AbortSignal`); el mock de `MODULE_REGISTRY` se amplió con `viewer-summary` y el redirect raíz del viewer cambió a `/t/acme/read/viewer-summary` (la otra aserción de viewer con deep-link a `/t/acme/analytics` no cambió porque la URL deep-linked se preserva).

#### UI-010.2 — Lectura · Analítica (34) — DONE (2026-05-14)
- **Alcance:** nueva vista read-only del rol Viewer en `src/features/viewer/analytics/`, aplicando el mockup `34 _ Lectura _ Analítica.html`. El orquestador `ViewerAnalytics.jsx` es un **wrapper fino** sobre el `AnalyticsPanel` legacy (`src/components/modules/analytics/AnalyticsPanel.jsx`) — el panel ya es **read-only por construcción** (no expone CTAs de export, edit ni descarga; sus únicos controles son selectores de rango/tab/refresh). Por eso se reusa **verbatim** sin tocar el legacy: 5 tests estáticos del backend (`test_analytics_static.py`, `test_analytics_agents_static.py`, `test_funnel_attribution_static.py`, `test_referrer_tracking_static.py`, `test_web_widget_static.py`) referencian el `AnalyticsPanel` en su path actual. El gating de permisos lo hace este orquestador con `<RequirePermission capability="analytics.tenant.read" mode="R">` (la capability ya existía en `permissions/matrix.js` — viewer = R; el backlog dice `analytics.read` como abreviación, la real es `analytics.tenant.read`). El `ReadOnlyShell` (UI-002) añade el banner permanente «Modo solo lectura». El nuevo módulo `viewer-analytics` se cableó en `moduleRegistry.js`, `data/modules.js` (label «Analítica», capability `analytics.tenant.read`) y `app/nav.js` (en `VIEWER_NAV` reemplaza a `analytics`; Owner/Admin/Manager/Agent siguen usando `analytics` directamente vía `TENANT_NAV`). El archivo más grande del feature es `ViewerAnalytics.test.jsx` con 132 LOC (orquestador 44 LOC). Cero CSS literales; el `.module.css` queda vacío porque el panel reusado trae su propio styling.
- **Diferencia intencional declarada:** el HTML del mockup muestra botones de «Exportar PDF» y similares; ese chrome no existe en `AnalyticsPanel` y no se va a inventar — no hay endpoint que lo soporte y el criterio global UI-010 («100% de las acciones write deben estar ocultas») se cumple por construcción.
- **Tests:** 3 frontend (`ViewerAnalytics.test.jsx`): render del panel reusado con eyebrow / heading / 4 tabs y los 7 endpoints de analítica disparados; NO se renderiza ningún `<button>` de export/descarga/copiar/editar/guardar (criterio UI-010); `AccessDenied` cuando el rol del tenant carece de `analytics.tenant.read`. `router.test.jsx` mantiene exactamente los 7 fallos de entorno documentados (Node-24 `undici`/`AbortSignal`); no se tocó el mock del registry porque el deep-link a `/t/acme/analytics` del test del viewer redirige al subárbol read-only **preservando el módulo deep-linked** — `analytics` sigue siendo una ruta válida bajo `/read/`.

#### UI-010.3 — Lectura · Citas (35) — DONE (2026-05-14)
- **Alcance:** nueva vista read-only del rol Viewer en `src/features/viewer/appointments/`, aplicando el mockup `35 _ Lectura _ Citas.html`. El orquestador `ViewerAppointments.jsx` monta `<RequirePermission capability="appointments.view" mode="R">` + `PageHeader` («Citas») + `AppointmentsFilters` + `AppointmentsList`, todo reusando los primitivos `Card`, `EmptyState`, `PageHeader`, `Pagination`, `FormField` y el componente de dominio `AppointmentCard` (con `appointmentStatusTone` ya mapeado). Helpers puros en `viewerAppointmentsData.js`: `STATUS_FILTER_OPTIONS` (confirmed / completed / pending / no_show / canceled — los cinco canónicos del mapa de tonos de `AppointmentCard`), `filterAppointments` (cliente-side por status / rango de fechas sobre `starts_at` / query libre contra `contact_label`), `paginate` (1-based, clamp-ea la página al rango válido), `toCsv` (header fijo `cliente,servicio,fecha,estado,recurso` + escape de comas/comillas/saltos), `downloadCsv` (Blob `text/csv;charset=utf-8` + `<a>` temporal; único helper impuro, espiable vía `URL.createObjectURL` en tests), `formatDateRange` (es-CO dateStyle medium + timeStyle short, degrada a `Sin fecha`). El hook `useViewerAppointmentsData` posee el estado de filtros + página + lista cruda traída por `listAppointments(session, tenantId)` sin parámetros de servidor (lo mismo que la vista Agente «Hoy · Citas del día», que ya filtra en cliente). `actions.exportCsv` corre sobre los registros **filtrados** (no sólo los paginados) — exportar la página visible sería contraintuitivo dado el spec del backlog («export-to-CSV opcional»). No se renderiza ningún `actions` slot en `AppointmentCard` ni `showPayment` — los Viewers no obtienen acciones de fila ni columnas de pago (criterio global UI-010). El nuevo módulo `viewer-appointments` se cableó en `moduleRegistry.js` (capability `appointments.view`), `data/modules.js` (label «Citas») y `app/nav.js` (en `VIEWER_NAV` reemplaza a `appointments`; Owner/Admin/Manager/Agent siguen usando `appointments`/`TodayAppointments` directamente vía `TENANT_NAV`). Todos los archivos del feature ≤ 400 LOC (el mayor, `viewerAppointmentsData.js`, ~165 LOC).
- **Diferencias intencionales declaradas:** el HTML del mockup muestra (a) un gráfico de «Citas por día · última semana» con día pico, (b) KPIs de «Atendidas / No-shows / Canceladas / Ticket promedio», (c) un panel «Estado de las citas · mayo» en proporción, (d) un bloque «Próximas citas destacadas» con miniaturas y (e) un CTA «Tomar handoff» por fila. Esos elementos asumen agregaciones (proyección, ocupación, ticket promedio) y acciones de escritura que no existen en el endpoint `listAppointments` (devuelve registros planos con `status`, `starts_at`, `service_name`/`service_code`, `resource_name` y `contact_label`). Se difieren — no se inventan datos ni se cablea CTAs de escritura, en línea con el criterio global UI-010 («100% de las acciones write deben estar ocultas»).
- **Tests:** 10 frontend (`viewerAppointmentsData.test.js` ×6: `STATUS_FILTER_OPTIONS` + `statusLabel`, `filterAppointments` por status / rango / query, `paginate` con casos de frontera (clamp arriba/abajo, lista vacía), `csvCell` (escapa comas/comillas/saltos), `toCsv` (header + filas + estado mapeado por etiqueta), `formatDateRange` (degrada a `Sin fecha`); `ViewerAppointments.test.jsx` ×4: render del listado + filtros + botón export para un viewer y `listAppointments` llamada sin filtros server-side, filtro de status reduce la lista visible, click en «Exportar CSV» dispara `URL.createObjectURL` con un Blob `text/csv;charset=utf-8` (spy en jsdom) y revoca la URL, `AccessDenied` cuando el rol del tenant carece de `appointments.view`). `router.test.jsx` mantiene exactamente los 7 fallos de entorno documentados (Node-24 `undici`/`AbortSignal`); el mock del registry no se tocó porque ningún test del router pinea `'appointments'` en `VIEWER_NAV` ni `'viewer-appointments'` por id.

#### UI-010.4 — Lectura · Conversaciones (36) — DONE (2026-05-15)
- **Alcance:** nueva vista read-only del rol Viewer en `src/features/viewer/conversations/`, aplicando el mockup `36 _ Lectura _ Conversaciones.html`. El orquestador `ViewerConversations.jsx` monta `<RequirePermission capability="conversations.view" mode="R">` + `PageHeader` («Conversaciones» + chip de resumen «N conversaciones · M con handoff») + el componente reusado `<InboxList>` con `showStartForm={false}`. El feature **reusa verbatim** la capa de datos del Inbox de Agente: el hook `useViewerConversationsData` es un wrapper fino sobre `useInboxData({ session, tenant })` que expone únicamente la rebanada read-only (`conversations`, `complaints`, `inboxFilter`, `setInboxFilter`) y el `summary` agregado por los helpers puros — NO re-consulta nada, NO expone `startForm` / `acceptHandoff` / `releaseHandoff` / message composer. El nuevo prop `showStartForm` de `InboxList` (default `true` preserva el comportamiento legacy de `OperationsDesk`) oculta el formulario «Iniciar conversación» que normalmente encabeza la lista — es una adición pura, sin cambios de comportamiento para los consumidores existentes (`OperationsDesk` no pasa nada y mantiene el default). El orquestador **no monta** `ConversationView` / `MessageComposer` / `ContactSidePanel` — los Viewers ven sólo la lista con sus `ConversationListItem` (badges + preview + timestamp), suficiente para el spec del backlog. El nuevo módulo `viewer-conversations` se cableó en `moduleRegistry.js` (capability `conversations.view`), `data/modules.js` (label «Conversaciones») y `app/nav.js` (en `VIEWER_NAV` reemplaza a `operations-desk`; Owner/Admin/Manager/Agent siguen usando `operations-desk`/`OperationsDesk` directamente vía `TENANT_NAV`). Helpers puros en `viewerConversationsData.js`: `CONVERSATIONS_DESCRIPTION`, `countByStatus`, `countWithHandoff`, `countUrgent`, `summarizeConversations` (reusa `isUrgentConversation` / `parseMeta` de `inboxData.js`, no duplica). Todos los archivos del feature ≤ 400 LOC (el mayor, `ViewerConversations.test.jsx`, ~137 LOC). **Cierra el bloque UI-010 (Viewer, 4 subtareas) Y todo el roadmap UI-006..UI-010 de rediseño por rol.** La siguiente tarea `PENDING` es **UI-011** (cross-cutting: ToastProvider, ConfirmDialog, ErrorBoundary, reemplazo de `window.alert`/`window.confirm`).
- **Diferencias intencionales declaradas:** el HTML del mockup muestra (a) una columna derecha con el detalle del mensaje + thread del contacto, (b) chips de SLA por fila y (c) CTAs «Tomar handoff» / «Liberar» por fila. Esos elementos exigen montar el `ConversationView` (que arrastra el `MessageComposer` con write actions) y/o las acciones de handoff (`acceptHandoff` / `releaseHandoff`), que están explícitamente prohibidas por el criterio global UI-010 («100% de las acciones write deben estar ocultas»). Se difieren — no se inventan datos ni se cablea CTAs de escritura.
- **Tests:** 9 frontend (`viewerConversationsData.test.js` ×5: descripción menciona «solo lectura», `countByStatus` agrega y omite filas sin `status`, `countWithHandoff` cuenta los tres estados de handoff, `countUrgent` cuenta solo `emergency`/`high` reusando `isUrgentConversation`, `summarizeConversations` agrega total/withHandoff/urgent/complaints y degrada a 0 con inputs inválidos; `ViewerConversations.test.jsx` ×4: render de la lista + tabs «Todas (N)» / «Quejas (M)» para un viewer y `listConversations` llamada con el tenant correcto, cambio a la tab de quejas muestra el mensaje vacío, **assert «zero write buttons»** — `queryByRole('button', { name: /iniciar conversación|enviar|tomar|liberar|aceptar handoff/i })` devuelve `null` cubriendo start-form / composer / handoff CTAs y verifica que las tabs SÍ existen (regex no tan ancho como para matchearlas), `AccessDenied` cuando el rol del tenant carece de `conversations.view` y los botones de write tampoco se montan en ese caso). `OperationsDesk.test.jsx` (5 tests previos del Inbox de Agente) sigue verde — el default `showStartForm=true` preserva el comportamiento original. `ReadOnlyShell.test.jsx` actualizado: el botón visible del Viewer ahora se llama «Conversaciones» (no «Operations Desk»). `router.test.jsx` mantiene exactamente los 7 fallos de entorno documentados (Node-24 `undici`/`AbortSignal`); el mock del registry no se tocó porque ningún test del router pinea `'viewer-conversations'` por id.

- **Criterios globales UI-010:**
  - 100% de las acciones write deben estar ocultas o renderizar `<DisabledCTA reason="read_only"/>`.
  - Test E2E: viewer abre `/t/acme/conversations` y NO encuentra ningún `<button>` write.
- **Dependencias:** UI-001..UI-005, UI-009.

---

### UI-011 — Cross-cutting: Toast, Modal global, Confirmaciones, Error boundaries

- **Estado:** DONE (2026-05-15)
- **Alcance:** se montan en el árbol de `App.jsx` los providers globales `ToastProvider` (ya existente, ahora envolviendo toda la app incluso el `LoginScreen`) y un nuevo `ConfirmProvider` que expone `useConfirm()` → `async confirm({ title, body, danger })` resuelto en una `<Modal>` (reusa la primitiva existente, no se crea un modal nuevo). Se añade `<ErrorBoundary>` (clase con `getDerivedStateFromError` + `componentDidCatch`) que envuelve el `Outlet` dentro de cada shell (`TenantShell`, `PlatformOwnerShell`, `ReadOnlyShell`) — el sidebar y el topbar quedan utilizables si una feature crashea; el fallback es una `<Card>` con "Algo salió mal" + botón "Reintentar"; un prop `onReport` opcional queda hookeado para sentry/audit (no se cablea reporter en este PR, lo asume una entrega posterior). Se barrieron las **20 llamadas nativas** de `window.confirm` distribuidas en **15 archivos** (managers/owner-admin/agente) reemplazándolas por `useConfirm()`; los `// Native confirm is preserved from the legacy module; UI-011 sweeps it.` desaparecen. `useConfirm()` cae a un stub `async () => true` si se invoca fuera del provider (test-friendly; en prod siempre hay provider). El comentario de cabecera en `DigestSubscriptionsPanel.jsx` se actualizó. **Diferido:** el `window.prompt` único en `useMediaLibraryData.js#editAssetTags` se deja como follow-up (un `TagPromptDialog` ⇒ siguiente PR); el criterio del backlog cubre solo `alert`/`confirm`.
- **Criterio:** `grep -rn "window.alert\|window.confirm" admin-panel/src` → **0 matches** (verificado).
- **Tests:** 4 tests en `ErrorBoundary.test.jsx`, 3 en `ConfirmDialog.test.jsx`, +1 nuevo en `Toast.test.jsx` (auto-dismiss con fake timers) — total **8 tests nuevos**. La suite full pasa con 432 tests verdes y solo los 7 fallos pre-existentes de `src/app/router.test.jsx` (Node-24 `undici`/`AbortSignal`, documentados desde UI-002). `OutboundDLQ.test.jsx` se migró del `vi.spyOn(window, 'confirm')` a un `vi.mock` del barrel UI con `useConfirm: () => async () => true`.
- **Dependencias:** UI-001.

---

### UI-012 — Theming + dark mode + branding por tenant (opcional)

- **Estado:** DONE (2026-05-15)
- **Alcance entregado (frontend-only):** dark-mode tokens en `tokens.css` (bloque `@media (prefers-color-scheme: dark)` + override explícito `:root[data-theme="dark"]`); `ThemeToggle` tri-estado (`auto/light/dark`) con persistencia `localStorage[copilotoia:theme]`; `TenantBrandLogo` que lee `tenant?.brand_logo_url` con fallback a iniciales; toggle + logo wireados al topbar vía `ShellTopbar`. Detalles en `docs/DONE.md`.
- **Follow-up backend (NO incluido en UI-012, pendiente):** añadir columna `brand_logo_url` a `app.tenant_settings`, extender el allowlist del PATCH `/tenants/{id}/settings`, agregar endpoint/form de upload. El backlog del backend lo recogerá como entrada separada (sugerido: `UI-012-FU`).
- **Dependencias:** UI-001.

---

### UI-013 — Accesibilidad y responsive

- **Estado:** DONE
- **Alcance:**
  - Auditar con `axe-core` (CI step nuevo) que cada feature pase ≥ 95 score.
  - Todas las vistas funcionales en viewport 360px.
  - Foco visible, navegación por teclado en sidebar, tablas con `role` y skip-link.
- **Criterios:** `npm run test:a11y` (alias para axe vía `vitest-axe`) pasa en CI (`Admin Panel — install, lint & build` job).
- **Dependencias:** UI-001 ... UI-010.

---

### UI-014 — Tests y CI

- **Estado:** DONE
- **Alcance:**
  - Añadir `vitest` + `@testing-library/react` + `@testing-library/user-event` a `admin-panel/`.
  - Pipeline `pnpm test` corre antes del `vite build` en CI.
  - Cobertura objetivo ≥ 60% en `components/ui/` y `permissions/`, ≥ 40% en `features/`.
- **Criterios:** GitHub Actions workflow añadido o existente extendido.
- **Dependencias:** UI-001.

---

### UI-015 — Limpieza final: borrar `admin-panel/src/components/modules/`

- **Estado:** DONE (2026-05-15)
- **Alcance:**
  - Una vez todas las features migradas a `src/features/`, borrar `src/components/modules/` y `src/data/modules.js`.
  - Borrar `src/hooks/useActiveModule.js`.
  - Borrar referencias en `AdminLayout` antiguo (ya removido en UI-002).
  - `grep -rn "components/modules" admin-panel/src` → 0.
- **Dependencias:** UI-006 ... UI-010.

---

### UI-012-FU — Backend support para `brand_logo_url`

- **Estado:** DONE (2026-05-15)
- **Origen:** follow-up declarado en `docs/DONE.md` durante UI-012 (frontend-only). El frontend ya pinta `tenant.brand_logo_url` cuando viene del backend con fallback a iniciales; falta toda la cadena server-side para persistirlo y devolverlo.
- **Alcance:**
  - Migración SQL: agregar columna `brand_logo_url text null` a `app.tenant_settings` (con check de longitud razonable, p. ej. ≤ 1024 chars).
  - Endpoint `PATCH /v1/tenants/{tenant_id}/settings`: añadir `brand_logo_url` al diccionario `allowed` (línea ~2412 de `app/api/v1/routes.py`).
  - Endpoint `POST /v1/tenants/{tenant_id}/branding/logo` (nuevo): upload del archivo, valida MIME (`image/png`, `image/jpeg`, `image/svg+xml`), tamaño máximo (p. ej. 512 KB), retorna la URL pública (S3/CDN o `/static/tenant-logos/{tenant_id}.{ext}`).
  - **Seguridad obligatoria:** mantener `authenticate_request` + `ensure_tenant_access` + RLS por tenant. SVG sanitizado (sin `<script>`, sin `xlink:href` a externos) — usar `defusedxml` o equivalente. URL whitelist si la imagen vive en CDN externo (anti-SSRF).
  - Auditoría: emitir `tenant_settings.branding_updated` por cada PATCH/upload (acción + actor + entity_id, como las otras mutaciones de settings).
  - UI admin: agregar el input/uploader en `TenantSetupWizard` (sección "Voz del bot / Branding") o en una pestaña dedicada de Config. Devuelve el `brand_logo_url` al `tenant_settings` actual; el shell lo recoge sin cambios.
- **Tests:**
  - Backend: pytest cubriendo (1) PATCH acepta `brand_logo_url` válido, (2) PATCH rechaza URL con SSRF / fuera del whitelist, (3) upload rechaza MIME inválido, (4) upload rechaza SVG con `<script>`, (5) audit log emitido. Mantener el patrón static-test del proyecto si aplica.
  - Frontend: actualizar el test de `TenantBrandLogo` para cubrir el caso `brand_logo_url` devuelto por el endpoint real (mockear `coreApi.getTenantSettings`).
- **Dependencias:** UI-012.

---

### UI-016 — Pantallas y componentes pendientes de diseño

- **Estado:** PENDING (bloqueado por entrega del diseñador)
- **Motivación:** la auditoría post-UI-015/UI-012 detectó vistas y estados implementados en código que no aparecen en los 36 HTML de `docs/HTML DESIGN/`. Sin diseño, se quedaron con look improvisado (defaults técnicos, EmptyState genérico, sin variantes mobile/dark). Esta tarea consolida la lista para pedírsela al diseñador y, una vez entregada, se trocea en subtareas `UI-016.x`.
- **Alcance — pantallas faltantes que el diseñador debe entregar:**
  1. **Vistas implementadas sin HTML asociado:**
     - `GoLiveReadiness` (Owner-Admin · checklist "listo para producción") — no aparece en 01-36.
     - `KnowledgeStorageSettings` (Owner-Admin · settings de almacenamiento del knowledge studio) — probablemente sección embebida del #18 pero sin layout propio definido.
     - `AnalyticsPanel` para Owner-Admin (módulo `analytics`) — se reusa el #24 del Manager; confirmar si Owner-Admin debe tener variante propia o compartir.
     - `AgentPerformance` (`owner-admin/analytics/AgentPerformance.jsx`) — tabla de performance por agente; sin layout en 01-36.
  2. **Rutas y estados intermedios sin diseño:**
     - `/no-tenant` (`NoTenantRoute`) — usuario autenticado sin tenant.
     - `/onboarding` (`OnboardingRoute`) — primer login antes de elegir tenant.
     - `MfaRequiredBlocker` — pantalla de bloqueo cuando el rol exige MFA y el usuario no la tiene inscrita.
     - `AccessDenied` — fallback cuando el rol no tiene la capability requerida.
     - 404 / ruta desconocida — hoy es `<Navigate to="/" replace />`; el diseñador debe decidir si hay vista propia "Página no encontrada" con CTA de regreso.
  3. **Flujos de cuenta de usuario totalmente ausentes:**
     - Perfil del usuario (nombre, foto, idioma personal).
     - Preferencias (notificaciones, idioma de UI, dark mode override por usuario en lugar de OS — relacionado a UI-012).
     - Logout / confirmación de cierre de sesión.
     - Selector inicial multi-tenant cuando el usuario tiene >1 tenant (hoy solo existe el switcher compacto del sidebar).
     - Cambio de contraseña / setup de MFA: hoy va por flujo externo de Auth0; confirmar si se quiere espejar en la UI.
  4. **Primitivas UI-011 / UI-012 sin diseño visual:**
     - `Toast` (notifications stack) — se shippeó con defaults técnicos.
     - `ConfirmDialog` — modal de confirmación; falta variante visual definida.
     - `ErrorBoundary` fallback — pantalla cuando un componente revienta.
     - `ThemeToggle` (icono sun/moon/auto) — diseño del control y posición fina en el topbar.
     - `TenantBrandLogo` slot — placement, sizing y estilo del fallback de iniciales.
  5. **Responsive (UI-013):**
     - Mockups explícitos para los viewports 360px y 768px por cada vista crítica. UI-013 cerró con un smoke de axe + collapse genérico a una columna; falta el diseño formal de la versión mobile de cada pantalla.
  6. **Documentación in-app:**
     - El archivo `docs/HTML DESIGN/00 _ Documentaci_n de acceso.png` parece un diagrama de roles/accesos. Confirmar con el diseñador si debe convertirse en una vista de ayuda/docs in-app o queda como referencia interna.
- **Procedimiento al recibir los diseños:**
  - Por cada HTML nuevo, agregarlo a `docs/HTML DESIGN/` siguiendo la convención `NN _ <area> _ <pantalla>.html`.
  - Crear subtareas `UI-016.1`, `UI-016.2`... cada una mapeada al HTML correspondiente, siguiendo la receta 0.bis.1 (tokens + bloques + primitivas reusadas).
  - Actualizar este UI-016 marcando cada subtarea cuando se cierre.
- **Dependencias:** UI-001 ... UI-015 (necesita el design system y las primitivas finales para reusar).

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

Después del cierre del roadmap principal (UI-001..UI-015 + UI-012) entran las
tareas de seguimiento:

- **UI-012-FU** — backend para `brand_logo_url`. Frontend-only de UI-012 ya está;
  esta tarea cierra la cadena server-side (migración + endpoint + upload).
- **UI-016** — pantallas pendientes de diseño. Bloqueada hasta que el diseñador
  entregue los HTMLs faltantes (lista detallada en la sección de la tarea).

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
