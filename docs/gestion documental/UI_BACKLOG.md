# UI Backlog — Módulo Gestión Documental con IA

> Backlog **independiente** del producto principal (`docs/UI_BACKLOG.md`). Cubre las vistas del admin-panel para los 19 roles del módulo de Gestión Documental, derivado de la Matriz de Roles, Permisos y Funciones (sección 10 — menús por rol). Ver `README.md` de esta carpeta para reglas y mandato.

Prefijo de consecutivos: **`GD-UI-NNNN`**. Prefijo de épicas: **`GD-UI-EP-NNN`**.

---

## Índice de épicas

| # | Épica | Rol primario | Entrega objetivo |
|---|---|---|---|
| EP-001 | Design system, routing y permisos | Todos | Entrega 1 |
| EP-002 | Ventanilla Única (radicador + coordinador) | ROL-004, ROL-005 | Entrega 2 |
| EP-003 | Buzón de trabajo unificado por rol | Todos los operativos | Entrega 3 |
| EP-004 | PQRSD (admin PQRSD + profesional + jefe) | ROL-006, ROL-007, ROL-008, ROL-009 | Entrega 4 |
| EP-005 | Correspondencia interna y externa | ROL-010, ROL-012, ROL-013 | Entrega 5 |
| EP-006 | Documentos + plantillas + firmas | ROL-014, ROL-017 | Entrega 6 |
| EP-007 | TRD/TVD + clasificación documental | ROL-003 | Entrega 8 |
| EP-008 | Administración del sistema y seguridad | ROL-001, ROL-002 | Entrega 1 |
| EP-009 | Auditoría + reportes + auditor | ROL-016 | Entrega 7 |
| EP-010 | IA asistida embebida en flujos | Todos los operativos | Entrega 7 |
| EP-011 | Bandeja de correo importado | ROL-004, ROL-005 | Entrega 7 |
| EP-012 | Notificaciones, alertas y comunicaciones | Todos | Entrega 3 |
| EP-013 | Periféricos de Ventanilla Única (impresión + digitalización + códigos) | ROL-001, ROL-004, ROL-005, ROL-016 | Entrega 2 (extiende EP-002) |

---

## 1. Heredar y extender el design system del producto principal

Toda tarea `GD-UI-NNNN` reutiliza:

- **Tokens raíz** ya definidos en `admin-panel/src/styles/tokens.css` (color, radio, sombra, tipografía — sección 0.bis.2 de `docs/UI_BACKLOG.md`).
- **Primitivas UI** existentes en `admin-panel/src/components/ui/`: Card, DataTable, Badge, Modal, FormField, EmptyState, KPI, Toast (la primera tarea del módulo principal `UI-002.x` ya las introduce; este módulo no las duplica).
- **Permisos** vía `admin-panel/src/permissions/matrix.js` — el módulo Gestión Documental añade un módulo paralelo `admin-panel/src/permissions/gd-matrix.js` con los 19 roles GD × ~140 permisos.

Lo que **sí** introduce este backlog específico:

- Componentes de dominio nuevos en `admin-panel/src/features/gd/components/`: `RadicadoCard`, `RadicadoConstanciaPreview`, `PQRSDStatusChip`, `TerminoVencimientoBadge`, `FirmaEvidenceModal`, `WorkflowTimeline`, `IASuggestionInline`, `DependenciaTreePicker`, `SerieSubseriePicker`, `ExpedienteIndice`.
- Rutas bajo el prefijo `/gd/*`. La sidebar muestra el ítem "Gestión Documental" como módulo top-level visible para los roles GD; ocultarlo si el usuario no tiene ni un permiso `gd.*`.
- Una landing distinta por rol GD (Radicador → `/gd/ventanilla`; Profesional → `/gd/buzon`; Jefe → `/gd/buzon/dependencia`; Admin PQRSD → `/gd/pqrsd`; Admin Documental → `/gd/trd`; Auditor → `/gd/auditoria`; Admin Sistema → `/gd/admin`).

## 2. Mandato de UI específico para Gestión Documental

Extiende el mandato general de `docs/UI_BACKLOG.md` con:

1. **Lenguaje institucional formal.** No usar copys conversacionales del producto principal ("¡Hola!", "Listo 🎉"). Mensajes en tono formal, tercera persona ("Se ha radicado", "El documento se encuentra"). El cliente público lee constancias y reportes — el lenguaje debe parecer Estado.
2. **Cero datos sensibles en URL.** Identificadores siempre por UUID, nunca el `numero_radicado` ni el documento del ciudadano en la barra. RNF-017.
3. **Confirmar acciones irreversibles.** Cualquier acción que altere estado oficial (clasificar, anular, firmar, aprobar, cerrar PQRSD, reasignar) abre un `ConfirmModal` con resumen y campo opcional/obligatorio de justificación (RNF-058, RNF-009).
4. **Trazabilidad visible.** Toda ficha (Radicado, PQRSD, Documento, Correspondencia, Expediente) muestra un componente `WorkflowTimeline` con eventos auditables del recurso. El timeline lee de `GET /api/v1/gd/auditoria?entidad_id=...` (GD-API-0019).
5. **Las sugerencias IA siempre son inline.** Nunca un modal aparte. Se muestran como callout dentro del formulario que correspondan (clasificación, dependencia, borrador de respuesta), con tres botones explícitos: **Aceptar**, **Modificar**, **Rechazar**. Ningún botón "Usar IA" automático que muta sin confirmar (RNF-029).
6. **Alcance visible.** Los listados que pueden mostrar info de otras dependencias deben tener un selector de alcance ("Mi dependencia" | "Mis dependencias autorizadas" | "Toda la entidad") visible y respetar permisos del backend.
7. **Constancias y reportes con marca institucional.** Los PDFs generados desde el frontend (constancias, reportes exportables) deben usar logo + nombre + NIT de `gd.entidad_publica` recuperados por API — no hardcodear branding de CopilotoIA en estos artefactos.
8. **Sin DELETE en la UI.** Ningún botón "Eliminar". Solo "Inactivar", "Anular", "Cerrar vigencia", "Reasignar", "Versionar".
9. **Estados con badges semánticos.** Mapeo fijo:
   - `nueva|registrado|borrador` → neutral
   - `en gestión|en revisión|en análisis|en proyección|asignada` → info azul
   - `aprobada|firmada|enviada|cerrada` → ok verde
   - `próxima a vencer|devuelta` → warn ámbar
   - `vencida|anulada|bloqueado|inactivo` → danger rojo
10. **Mobile-first secundario.** El uso primario es escritorio (radicador en counter, jefe revisando, profesional proyectando). La versión móvil prioriza consulta + buzón + notificaciones; las pantallas de configuración y catálogos pueden ser desktop-only. RNF-034.

## 3. Mapping rol → landing y módulos visibles

Derivado de la Matriz de Roles sección 10.

| Rol GD | Landing | Sidebar visible |
|---|---|---|
| ROL-001 Admin Sistema | `/gd/admin/usuarios` | Admin · Usuarios · Roles · Dependencias · Cargos · Canales · Parámetros · Integraciones |
| ROL-002 Admin Seguridad | `/gd/seguridad` | Seguridad · Usuarios · Sesiones · Auditoría seguridad |
| ROL-003 Admin Documental | `/gd/trd` | TRD · TVD · Series · Subseries · Tipos documentales · Expedientes · Auditoría documental |
| ROL-004 Radicador VU | `/gd/ventanilla` | Ventanilla · Nuevo radicado · Correos por procesar · Constancias · Reportes VU |
| ROL-005 Coordinador VU | `/gd/ventanilla/cola` | Ventanilla · Cola pendientes · Reasignaciones · Anulaciones · Reportes VU |
| ROL-006 Admin PQRSD | `/gd/pqrsd` | Panel PQRSD · Nuevas · Sin asignar · Por vencer · Vencidas · Reportes PQRSD |
| ROL-007 Profesional | `/gd/buzon` | Mi buzón · PQRSD asignadas · Correspondencia · Tareas · Borradores |
| ROL-008 Revisor | `/gd/buzon` (filtro revisar) | Mi buzón · Documentos por revisar · Documentos por dar VB |
| ROL-009 Jefe Dependencia | `/gd/buzon/dependencia` | Buzón dependencia · PQRSD dep · Por aprobar · Por firmar · Reasignaciones · Reportes dep |
| ROL-010 Secretario Dependencia | `/gd/buzon/dependencia` (RW limitado) | Buzón dependencia · Correspondencia dep · Borradores |
| ROL-011 Usuario Dependencia | `/gd/buzon` | Mi buzón · Mis tareas · Mis borradores |
| ROL-012 Usuario Comunicación Interna | `/gd/correspondencia/interna` | Correspondencia interna · Nueva · Recibidas · Enviadas |
| ROL-013 Usuario Radicación Externa | `/gd/correspondencia/externa` | Correspondencia externa · Borradores · Por revisar · Por firmar · Enviadas |
| ROL-014 Firmante | `/gd/firmas/por-firmar` | Firmas · Por firmar · Firmadas · Rechazadas · Evidencia |
| ROL-015 Usuario Consulta | `/gd/consulta` | Consulta · Radicados · Documentos · Trazabilidad (todo solo-lectura) |
| ROL-016 Auditor | `/gd/auditoria` | Auditoría · Eventos · Reportes · Trazabilidad · Vencimientos · Anulaciones · Reasignaciones |
| ROL-017 Admin Plantillas | `/gd/plantillas` | Plantillas · Versiones · Asociaciones |
| ROL-018 Agente IA | (sin UI — solo backend) | — |
| ROL-019 Robot RPA | (sin UI — solo backend) | — |

## 4. Definition of Done por vista

Cada `GD-UI-NNNN` debe entregar:

1. Ruta declarada en `admin-panel/src/features/gd/routes.tsx` con `loader`/`element` y gate de permisos.
2. Componente principal en `admin-panel/src/features/gd/<feature>/<Vista>.tsx` (≤ 400 líneas; troceado en subcomponentes/hooks si excede).
3. Hooks de data (`useGdRadicado`, `useGdPQRSD`, etc.) en `admin-panel/src/features/gd/hooks/` que envuelven los endpoints del backlog API.
4. Tests con `vitest + @testing-library/react`: render con rol permitido, render con rol no permitido (espera vacío o redirect), interacción crítica del flujo.
5. Screenshot adjunto al PR (viewport 1440×900).
6. Verificación de tokens: `grep -E "color: #|background: #|border-radius: [0-9]" src/features/gd/<feature>/` no encuentra literales hardcodeados.
7. Storybook story por cada nueva primitiva de dominio (si se introduce).

---

## EP-001 — Design system, routing y permisos GD

### GD-UI-0001 — Matriz de permisos GD y guard de rutas
- **Crea:** `admin-panel/src/permissions/gd-matrix.ts` con los 19 roles × ~140 permisos del módulo (traducidos del PDF Matriz de Roles).
- **Crea:** wrapper `<GdRouteGuard requires={['PERM-VU-001']} alcance="dependencia"/>` que delega validación final al backend pero oculta menús y rutas en frontend.
- **Aceptación:** un usuario con solo ROL-007 no ve los items "Admin", "TRD", "Auditoría", "Plantillas" en la sidebar.

### GD-UI-0002 — Sidebar y top bar de Gestión Documental
- **Crea:** `<GdSidebar />` que arma el árbol de navegación a partir del usuario actual y la matriz GD; `<GdTopBar />` con buscador global (RNF-039: buscar por número de radicado desde cualquier vista).
- **Reglas:** un usuario sin permisos GD no ve la sección entera (el ítem "Gestión Documental" del nav principal se oculta).

### GD-UI-0003 — Tokens institucionales para constancias y reportes
- Define `--gd-print-margin`, `--gd-print-header-h`, `--gd-print-footer-h` para hojas A4 y letter (RNF-040 + RNF-014).
- Crea componente `<InstitutionalLetterhead />` que consume `GET /api/v1/gd/entidad` y renderiza logo + datos.

### GD-UI-0004 — Componentes de dominio compartidos
- Implementa `RadicadoCard`, `PQRSDStatusChip`, `TerminoVencimientoBadge` (semáforo según GD-API-0042), `WorkflowTimeline` (RNF-012), `JustificacionRequiredField`, `DependenciaPicker`, `UsuarioPicker` (con filtro por dependencia + rol), `SerieSubseriePicker` (con filtro por versión TRD vigente).
- Cada componente con storybook + tests.

### GD-UI-0005 — Hook genérico `useGdAudit(entidadTipo, entidadId)`
- Devuelve la lista paginada de eventos auditables para mostrar en `<WorkflowTimeline />` reutilizable en Radicado, PQRSD, Documento, Correspondencia, Expediente, Usuario.

### GD-UI-0006 — Layout específico GD con breadcrumbs y alcance
- `<GdShell />` que envuelve todas las vistas con breadcrumbs auto-generados y un `<ScopeSelector />` global (Mi dependencia | Mis dependencias autorizadas | Toda la entidad) que persiste en el store y filtra todas las queries.

---

## EP-002 — Ventanilla Única

**Roles:** ROL-004 Radicador, ROL-005 Coordinador.
**Endpoints consumidos:** GD-API-0024 a GD-API-0032.

### GD-UI-0007 — Pantalla "Nuevo radicado de entrada"
- Formulario en pasos: 1) Canal y remitente (con búsqueda de tercero o creación inline — depende de GD-UI-0017), 2) Asunto y descripción + sugerencia IA inline opcional (`POST /api/v1/gd/ia/extraer`), 3) Anexos (drag & drop con validación), 4) Clasificación inicial (con sugerencia IA — GD-UI-0027), 5) Confirmación → muestra `numero_radicado` + constancia con QR.
- **RNF:** RNF-003 (response time visible), RNF-014 (constancia con datos institucionales), RNF-044 (validación de duplicados de tercero).

### GD-UI-0008 — Pantalla "Nuevo radicado de salida"
- Selector de radicado de entrada relacionado (opcional), documento adjunto (solo aprobados/firmados), dependencia origen, destinatario.

### GD-UI-0009 — Cola de radicados pendientes de clasificación
- DataTable filtrable por canal, fecha, asunto. Acción "Clasificar" abre drawer lateral con la pantalla 4 de GD-UI-0007.
- **Rol:** ROL-004 ve su cola; ROL-005 ve la cola de toda la VU.

### GD-UI-0010 — Constancias y QR de verificación
- Vista `<RadicadoConstanciaPreview />` que renderiza la constancia tal como la verá el ciudadano (HTML imprimible con `<InstitutionalLetterhead />` + QR + leyenda con código de verificación).
- Pantalla pública (sin auth) `/gd/verificar/{codigo}` consume GD-API-0030 y muestra estado actual del radicado.

### GD-UI-0011 — Flujo de anulación de radicado (solicitar + aprobar)
- En la ficha del radicado, botón "Solicitar anulación" abre modal con campo motivo obligatorio.
- Vista `/gd/ventanilla/anulaciones` lista solicitudes pendientes; el aprobador (PERM-VU-016) puede aprobar/rechazar con observación.
- **RNF:** RNF-058. Validación: solicitante ≠ aprobador.

### GD-UI-0012 — Reclasificación y corrección menor con justificación
- Acciones contextuales en la ficha del radicado, ambas solicitan justificación.

### GD-UI-0013 — Búsqueda global de radicados
- Vista `/gd/ventanilla/buscar` con filtros: número, tercero, asunto, estado, fecha, dependencia, serie, vencimiento, canal.
- Respeta alcance del usuario (RNF-039 + RNF-021).

### GD-UI-0014 — Reportes de Ventanilla
- Tableros con radicados por fecha, por canal, por dependencia, anulaciones, reasignaciones. Botón "Exportar" en PDF/Excel/CSV (PERM-REP-004).

### GD-UI-0015 — Ficha de radicado con timeline completo
- Vista `/gd/ventanilla/radicados/{id}` con tabs: General, Anexos, Clasificación (historial), Trazabilidad (`<WorkflowTimeline />`), Acciones permitidas.
- En la pestaña Trazabilidad, cada evento muestra usuario + rol + dependencia + cargo del momento (RNF-006, RNF-009).

---

## EP-003 — Buzón de trabajo

**Roles:** todos los operativos.
**Endpoints:** GD-API-0038, GD-API-0039.

### GD-UI-0016 — Mi Buzón
- Layout tipo Gmail/Outlook con barra lateral de carpetas:
  - PQRSD asignadas (badge con conteo + vencimientos próximos)
  - Correspondencia recibida
  - Correspondencia enviada
  - Tareas pendientes
  - Borradores
  - Documentos por revisar
  - Documentos por aprobar
  - Documentos por firmar
  - Notificaciones
  - Alertas
- Panel central: lista de ítems con preview; panel derecho: detalle del ítem seleccionado.
- **RNF:** RNF-021, RNF-022.

### GD-UI-0017 — Buzón de dependencia
- Misma estructura que GD-UI-0016 pero scoped a dependencia. Visible para ROL-009/ROL-010 con alcance correspondiente.
- Vista adicional: "Carga de trabajo del equipo" — KPI por usuario con tareas abiertas, vencimientos, productividad (PERM-REP-009).

### GD-UI-0018 — Tarea genérica: detalle + acciones
- Ficha de Tarea con `WorkflowTimeline` + acciones (`iniciar`, `devolver`, `finalizar`, `reasignar`, `escalar`).
- Reasignar abre `<UsuarioPicker />` filtrado por dependencia y rol compatible.

### GD-UI-0019 — Reasignación masiva al inactivar usuario
- Cuando un Admin Sistema inactiva un usuario con tareas pendientes, se abre wizard que lista las tareas y permite reasignarlas en lote a otro funcionario.
- Disparado desde `GD-UI-0066` (gestión de usuarios).

---

## EP-004 — PQRSD

**Roles:** ROL-006, ROL-007, ROL-008, ROL-009.
**Endpoints:** GD-API-0043 a GD-API-0051.

### GD-UI-0020 — Panel PQRSD del administrador
- KPIs: nuevas, sin asignar, asignadas, en gestión, próximas a vencer, vencidas, cerradas, tiempo promedio.
- Filtros: tipo PQRSD, dependencia, estado, semáforo de vencimiento.

### GD-UI-0021 — Lista de PQRSD con semáforo de vencimiento
- DataTable con columna `<TerminoVencimientoBadge />` (verde > 50% del plazo, ámbar 25-50%, rojo < 25% o vencido).
- Acciones contextuales según permisos: Clasificar, Asignar, Reasignar, Cerrar, Trasladar competencia.

### GD-UI-0022 — Ficha de PQRSD
- Tabs: General (datos + tercero + asunto + descripción + sugerencia IA de resumen — GD-API-0080), Anexos, Respuestas (proyectadas/aprobadas/firmadas), Trazabilidad, Notas internas, Acciones.

### GD-UI-0023 — Workflow de proyección de respuesta
- Botón "Proyectar respuesta" abre editor con dos opciones: redactar desde cero o generar desde plantilla. Si elige plantilla, llama a GD-API-0065 y muestra el documento generado (descarga DOCX para edición externa en v1).
- Cargar versión ajustada → crea nueva versión del documento (GD-API-0059).

### GD-UI-0024 — Workflow revisar / aprobar / firmar
- Pantallas separadas por permiso:
  - Revisor (PERM-PQRSD-013): ve docs en revisión, botones Aprobar VB / Devolver con observaciones.
  - Jefe (PERM-PQRSD-015): ve docs aprobados pendientes de firma o que requiere su aprobación.
  - Firmante (PERM-PQRSD-016): integra con EP-006 firmas.

### GD-UI-0025 — Cierre y reapertura de PQRSD
- Cerrar requiere respuesta enviada o causal explícita; reapertura requiere justificación + permiso PERM-PQRSD-020.

### GD-UI-0026 — Traslado por competencia y solicitud de información adicional
- Acciones especiales en la ficha. Traslado genera oficio desde plantilla GD-API-0049. Solicitud de info pausa el término y notifica (GD-API-0050).

### GD-UI-0027 — Suspensión del término registrada
- Pantalla `/gd/pqrsd/{id}/suspensiones` lista historial de suspensiones; agregar suspensión actualiza la fecha límite y deja trazabilidad (PERM-PQRSD-023).

### GD-UI-0028 — Reportes PQRSD
- Dashboard: por tipo, por dependencia, vencidas, próximas, tiempo promedio (PERM-REP-006). Exportable.

---

## EP-005 — Correspondencia interna y externa

**Roles:** ROL-010, ROL-012, ROL-013.

### GD-UI-0029 — Correspondencia interna: crear y enviar
- Editor formal con destinatario(s) (usuarios o dependencias), asunto, cuerpo, anexos. Valida regla de comunicación entre dependencias (GD-API-0016).
- Botones: Guardar borrador · Enviar.

### GD-UI-0030 — Bandeja interna recibidas/enviadas
- Lista paginada con filtros y badge de lectura. Vista detalle muestra cuerpo, anexos, historial de respuestas/reenvíos.

### GD-UI-0031 — Correspondencia externa: borrador + workflow completo
- Editor para crear oficio externo de salida. Asocia radicado de entrada si aplica. Envía a revisión, aprobación y firma.
- Permite "Solicitar radicación de salida a Ventanilla" o "Radicar directa" (si tiene PERM-CE-009).

### GD-UI-0032 — Registrar soporte de envío
- Tras enviar, el usuario registra evidencia (PDF de acuse, captura de email, guía courier) — PERM-CE-011.

### GD-UI-0033 — Múltiples destinatarios y copias
- Componente `<DestinatariosCorrespondenciaInput />` soporta principal, copia, copia oculta.

### GD-UI-0034 — Anulación de correspondencia con autorización
- Mismo patrón que anulación de radicado: solicitud + aprobación + auditoría.

---

## EP-006 — Documentos, plantillas y firmas

**Roles:** ROL-014 Firmante, ROL-017 Admin Plantillas, ROL-007/008/009 como consumidores.

### GD-UI-0035 — Biblioteca de documentos
- Lista filtrable de documentos por tipo, estado, dependencia, expediente, serie/subserie. Acciones según permiso.

### GD-UI-0036 — Ficha de documento con historial de versiones
- Tabs: Actual (preview + metadatos), Versiones (lista cronológica con quién/cuándo/observación), Firmas, Asociaciones (radicado, PQRSD, correspondencia, expediente), Trazabilidad.
- Descarga audita la consulta (RNF-059) si la clasificación es reservada o superior.

### GD-UI-0037 — Carga de documento o anexo con validación
- `<FileUpload />` con validación de tipo, tamaño y estado de antivirus en tiempo real. Si el archivo queda bloqueado, muestra mensaje claro.

### GD-UI-0038 — Reemplazo y anulación de documentos
- Botones contextuales con justificación obligatoria.

### GD-UI-0039 — Administrador de plantillas
- CRUD de plantillas + editor de campos dinámicos. Permite subir DOCX base + mapear placeholders.
- Asociar plantilla a dependencia y tipo de trámite.
- **Rol primario:** ROL-017.

### GD-UI-0040 — Generación de documento desde plantilla
- Componente `<GenerarDesdeplantilla />` integrado en flujos PQRSD y Correspondencia. Muestra preview previo + permite descarga o ajuste.

### GD-UI-0041 — Bandeja "Por firmar"
- Lista de documentos que esperan firma del usuario actual. Cada item con preview + datos del trámite + botones Firmar | Rechazar con observación.
- Firmar pide confirmación + opcionalmente step-up (re-introducir password si pasaron > 5 min desde último login — RNF-005).

### GD-UI-0042 — Registro de firma escaneada
- Pantalla `/gd/firmas/escaneada` permite al usuario subir su firma digitalizada para usos autorizados (PERM-FIR-003). Solo si la política institucional lo habilita.

### GD-UI-0043 — Evidencia de firma
- Modal accesible desde cualquier documento firmado: hash, IP, fecha, snapshot del firmante (cargo, dependencia, rol al momento).
- **RNF:** RNF-016 último criterio.

### GD-UI-0044 — Configuración de firmantes autorizados
- Vista de Admin Sistema para definir qué usuarios tienen permiso PERM-FIR-001 para qué tipos de documento o dependencia.

---

## EP-007 — TRD, TVD y clasificación documental

**Rol primario:** ROL-003 Admin Documental.

### GD-UI-0045 — CRUD de TRD con versiones
- Lista de TRD con su versión vigente; abrir versión muestra estructura jerárquica de series/subseries.
- Botón "Crear nueva versión" abre wizard que clona desde la versión anterior.

### GD-UI-0046 — CRUD de TVD con versiones
- Mismo patrón que TRD.

### GD-UI-0047 — Editor jerárquico de Series → Subseries → Tipos documentales
- Drag & drop para reordenar; campos por nodo: código, nombre, descripción, tiempo en archivo de gestión/central, disposición final.

### GD-UI-0048 — Asociar dependencia ↔ código documental
- Tabla cruzada dependencia × serie; marcar/desmarcar.

### GD-UI-0049 — Clasificación documental de un documento o radicado
- Componente `<SerieSubseriePicker />` se invoca desde la ficha del documento o radicado (acción "Clasificar documentalmente"). Filtra según dependencia y versión TRD vigente.

### GD-UI-0050 — Consulta de clasificación histórica
- Dado un documento, mostrar la versión TRD/TVD vigente al momento de su clasificación (RNF-025).

### GD-UI-0051 — Expediente electrónico básico
- Vista `/gd/expedientes` con CRUD, asociación de documentos y radicados, cierre con justificación.
- `<ExpedienteIndice />` muestra contenido ordenado del expediente.

---

## EP-008 — Administración del sistema y seguridad

**Roles:** ROL-001, ROL-002.

### GD-UI-0052 — Configuración institucional (entidad pública)
- Editor de datos: nombre, NIT, dirección, teléfonos, correos, logo (upload). Cambios sensibles requieren confirmación + justificación.

### GD-UI-0053 — Editor de estructura orgánica versionada
- Árbol de dependencias jerárquico. Acciones: crear, renombrar (abre nueva versión), fusionar, cerrar vigencia. Cambios afectan solo a nueva versión.
- Visualizador histórico: "¿Cómo se veía la estructura el 2024-06-15?"

### GD-UI-0054 — Gestión de cargos
- CRUD con vigencias.

### GD-UI-0055 — Catálogos: canales, tipos PQRSD, tipos correspondencia, estados
- Tabla maestra con CRUD por catálogo.

### GD-UI-0056 — Calendario institucional (hábiles + feriados)
- Vista calendario donde el admin marca feriados, días no hábiles especiales.
- **RNF:** RNF-023.

### GD-UI-0057 — Parámetros institucionales clave-valor
- Tabla editable con tooltip de descripción y vigencia. Cambio de parámetro crítico abre confirmación.

### GD-UI-0058 — Gestión de usuarios (CRUD)
- Lista con filtros (estado, dependencia, rol, tipo vinculación, fecha de fin vinculación).
- Crear/editar usuario; al inactivar dispara GD-UI-0019.

### GD-UI-0059 — Asignación de roles a usuarios con alcance
- En la ficha del usuario, sección "Roles activos" + "Historial de roles". Asignar nuevo rol con dependencia y vigencia. Cerrar rol con motivo.

### GD-UI-0060 — Editor de roles y matriz rol↔permiso
- Lista de roles + para cada rol, checklist de permisos agrupados por módulo.
- Vista solo-lectura "Matriz completa" (renderiza el contenido de `MATRIZ_PERMISOS.md`).

### GD-UI-0061 — Política de contraseñas y seguridad
- Form para política (longitud, complejidad, historial, vigencia, intentos fallidos, cooldown).
- Rol primario: ROL-002.

### GD-UI-0062 — Sesiones activas y cierre forzado
- Lista de sesiones activas por usuario. Botón "Cerrar sesión" (PERM-USR-012).

### GD-UI-0063 — Configuración de buzones de correo institucional
- CRUD de buzones, credenciales referenciadas a vault (no se muestran en claro). Test de conexión.
- **Rol:** ROL-001 con PERM-COR-001.

### GD-UI-0064 — Configuración de proveedor IA y políticas de uso
- Selección del proveedor (Claude / OpenAI / local), prompts base por tipo de asistencia, política de redacción de datos sensibles (RNF-029, RNF-086).

### GD-UI-0065 — Identidades técnicas (Agente IA, Robot RPA)
- Creación y rotación de credenciales para usuarios técnicos. Auditado.

### GD-UI-0066 — Reglas de comunicación entre dependencias
- Matriz origen × destino + flag "requiere aprobación de jefe".

---

## EP-009 — Auditoría, reportes y vista del Auditor

**Rol primario:** ROL-016.

### GD-UI-0067 — Consulta de auditoría con filtros avanzados
- Filtros: tipo de evento, usuario, dependencia, entidad afectada, criticidad, rango de fechas.
- Tabla con expansión por fila mostrando `valor_anterior` y `valor_nuevo` formateados como diff JSON.
- Exportable (RNF-054, PERM-AUD-007).

### GD-UI-0068 — Reportes consolidados
- Catálogo de reportes ejecutables: radicados, PQRSD, correspondencia, vencimientos, anulaciones, reasignaciones, accesos a info sensible, uso de IA, carga de trabajo.
- Cada reporte permite parámetros + export PDF/Excel/CSV.

### GD-UI-0069 — Dashboard del auditor
- KPIs institucionales: total radicados, PQRSD vencidas, tasa de cumplimiento, eventos críticos del último mes, accesos a info reservada.

### GD-UI-0070 — Trazabilidad por entidad
- Buscador "Ver historial de" → selecciona radicado / PQRSD / documento / usuario y muestra `<WorkflowTimeline />` completo.

### GD-UI-0071 — Reportes de uso de IA
- Sugerencias generadas, aceptadas, modificadas, rechazadas. Por usuario y por tipo de asistencia (PERM-AUD-006).

---

## EP-010 — IA asistida embebida en flujos

> Esta épica no introduce vistas nuevas — añade componentes que se incrustan en las vistas ya definidas. Las tareas se ordenan por flujo donde aparecen.

### GD-UI-0072 — Componente `<IASuggestionInline />`
- Card insertado dentro de un formulario; muestra el resultado IA con `confianza`, `explicacion`, y tres botones Aceptar/Modificar/Rechazar.
- Al aceptar, dispara endpoint humano correspondiente y materializa el cambio. Al modificar, abre editor inline. Al rechazar, pide motivo opcional.
- **RNF:** RNF-029.

### GD-UI-0073 — Sugerencia de clasificación en Ventanilla
- En GD-UI-0007 paso 4: una llamada a `POST /api/v1/gd/ia/clasificar` propone el tipo + sub-tipo; el radicador acepta/modifica/rechaza.

### GD-UI-0074 — Sugerencia de dependencia responsable en PQRSD
- En GD-UI-0021/0022: botón "Sugerir dependencia" llama a GD-API-0081 y muestra top-3 candidatas con score.

### GD-UI-0075 — Resumen del caso en ficha de PQRSD
- En GD-UI-0022 tab General: componente que solicita resumen a GD-API-0080 y lo muestra en una card colapsable.

### GD-UI-0076 — Borrador inicial de respuesta IA
- En GD-UI-0023: opción "Generar borrador con IA" llama a GD-API-0083; el funcionario puede aceptar tal cual, modificar inline o rechazar.

### GD-UI-0077 — Detección de duplicados al radicar
- En GD-UI-0007 paso 2: llamada a GD-API-0082 con asunto + descripción; muestra "Posibles duplicados encontrados" como warning con links.

### GD-UI-0078 — Extracción de datos del correo
- En GD-UI-0080: al abrir un correo importado, la IA propone tercero, asunto, anexos extraídos. El usuario valida antes de convertir en radicado.

---

## EP-011 — Bandeja de correo institucional

**Roles:** ROL-004, ROL-005.

### GD-UI-0079 — Lista de correos pendientes de procesar
- Vista `/gd/correo/pendientes` con buzones configurados + contador. DataTable de correos no procesados.

### GD-UI-0080 — Detalle de correo importado
- Preview del correo (asunto, remitente, cuerpo, anexos), card con extracción IA (GD-UI-0078), botones "Convertir en radicado", "Asociar a radicado existente", "Descartar".

### GD-UI-0081 — Asociar correo a radicado existente
- Buscador de radicado + confirmación. Al asociar, los anexos quedan en el radicado y el correo se marca como procesado.

### GD-UI-0082 — Descarte de correo con motivo
- Modal con motivo obligatorio. Eventos auditados (no se borra el correo, solo se marca `descartado`).

---

## EP-012 — Notificaciones, alertas y comunicaciones

### GD-UI-0083 — Centro de notificaciones in-app
- Dropdown desde la top bar con últimas N notificaciones; vista expandida `/gd/notificaciones`. Marcar como leída.

### GD-UI-0084 — Centro de alertas críticas
- Lista priorizada por severidad. Para vencimientos PQRSD muestra cuenta regresiva. Permite escalar al jefe (PERM-NOT-006).

### GD-UI-0085 — Preferencias del usuario para notificaciones
- Por tipo de evento: in-app on/off, correo on/off. Persistido por usuario.

### GD-UI-0086 — Banner de alertas críticas globales
- Si hay PQRSD vencidas del usuario actual o de su dependencia (si es jefe), banner persistente arriba de la pantalla con CTA al detalle.

---

## EP-013 — Periféricos de Ventanilla Única (impresión + digitalización + códigos)

**Roles:** ROL-001 Admin Sistema (registra hardware), ROL-005 Coordinador VU (configura puntos), ROL-004 Radicador (opera), ROL-016 Auditor (consulta historial).
**Endpoints consumidos:** GD-API-0128 a GD-API-0142.
**Doc fuente:** Doc 5 v0.1-rev1 § 28 + Doc 6 v0.1 completo (RFP-001..008).
**Mandato específico:**
- **Esta épica solo se renderiza** cuando `gd.organizacion_modulo_activacion.modulo_codigo='ventanilla_presencial_con_perifericos'`. Si la organización no lo activa, los menús, botones y rutas de esta épica no existen.
- **El agente local** se instala fuera de este admin-panel. Esta UI envía instrucciones al backend; el backend las enruta al agente local autenticado. La UI no habla directamente con hardware.
- **Estado del agente visible:** el header de Ventanilla Única muestra un indicador (verde / ámbar / rojo) del agente local del punto actual. Si el agente está offline, los botones de impresión/digitalización se deshabilitan con tooltip explicativo.

### GD-UI-0087 — Pantalla de administración de periféricos
- **Ruta:** `/gd/admin/perifericos`.
- **Rol:** ROL-001 Admin Sistema. Permiso PERM-PER-001.
- **Vista:** `DataTable` con columnas: Nombre, Tipo (impresora etiquetas / impresora térmica / escáner plano / escáner automático / lector códigos), Marca, Modelo, Serial, Punto de atención, Dependencia, Estado (badge semántico), Última operación.
- **Filtros:** punto de atención, tipo, estado.
- **Acciones:** Registrar nuevo (modal con form), Editar configuración (drawer lateral), Activar/Inactivar/Mantenimiento/Retirar (con motivo), Ver historial (link a GD-UI-0094).
- **Endpoints:** `GET/POST /api/v1/gd/perifericos`, `PATCH /api/v1/gd/perifericos/{id}`, `POST /api/v1/gd/perifericos/{id}/activar|inactivar|poner-mantenimiento|retirar`.
- **Componente nuevo:** `<PerifericoStatusBadge />` con semáforo (activo=verde, mantenimiento=ámbar, inactivo/retirado=rojo, registrado pero no probado=neutral).
- **Validaciones:** serial único por organización (feedback inline al teclear); al inactivar muestra warning si tiene operaciones del último día.
- **Aceptación:** un admin registra una Zebra GK420t en el "Punto Principal"; aparece en la tabla; intentar registrar otra con el mismo serial falla con mensaje claro.

### GD-UI-0088 — Pantalla de puntos de atención
- **Ruta:** `/gd/admin/puntos-atencion`.
- **Rol:** ROL-001, ROL-005. Permiso PERM-PER-001.
- **Vista:** lista de puntos con expansión para mostrar periféricos asignados. Cada punto muestra dirección, dependencia responsable, número de periféricos activos y estado del agente local.
- **Acciones:** Crear/Editar punto, Asignar periféricos (modal de transferencia), Cerrar punto (con flujo de reasignación de periféricos).
- **Endpoints:** `GET/POST/PATCH /api/v1/gd/puntos-atencion`, `GET /api/v1/gd/puntos-atencion/{id}/perifericos`.
- **Aceptación:** crear "Sede Sur"; asignar 2 impresoras y 1 escáner; cerrar el punto pide reasignar/desactivar los periféricos antes (no permite huérfanos).

### GD-UI-0089 — Botones de impresión en ficha de radicado
- **Ubicación:** ficha de radicado (GD-UI-0015) — barra de acciones lateral.
- **Rol:** ROL-004 (con PERM-PER-003 y PERM-PER-005).
- **Botones:**
  - **"Imprimir etiqueta"** → modal con selector de periférico activo del punto actual + selector de formato (estándar/compacta/sticker) + checkboxes QR/código barras → llama `POST /api/v1/gd/perifericos/{id}/imprimir-etiqueta`.
  - **"Imprimir constancia"** → modal con selector de periférico + formato → llama `POST /api/v1/gd/perifericos/{id}/imprimir-constancia`.
  - **"Generar código QR/barras"** → modal con tipo → llama `POST /api/v1/gd/radicados/{id}/codigo-barras` y muestra preview.
- **Componente nuevo:** `<EtiquetaPreview />` que renderiza cómo se verá la etiqueta (basado en el `archivo_digital_id` que devuelve el backend).
- **Estados visibles:** toast "Enviando a impresora..." → "Impresa correctamente" (success) o "Fallo de impresión" (error con detalle).
- **Validaciones:** si no hay periférico activo del tipo correcto, el botón se deshabilita con tooltip "No hay impresoras de etiquetas configuradas en este punto".
- **Aceptación:** radicador imprime etiqueta de `RAD-2026-001234` desde Counter-1; aparece toast de éxito; al escanear el QR de la etiqueta resuelve al radicado.

### GD-UI-0090 — Componente de digitalización en wizard de radicado entrada
- **Ubicación:** paso 3 (Anexos) del wizard de GD-UI-0007.
- **Rol:** ROL-004. Permiso PERM-PER-006.
- **Funcionalidad:**
  - Botón **"Escanear documento"** además del "drag & drop" tradicional.
  - Modal con selector de escáner del punto + calidad DPI (200/300/600) + observación opcional.
  - Al confirmar, llama `POST /api/v1/gd/perifericos/{id}/digitalizar` y muestra spinner "Escaneando..." con barra de progreso.
  - Cuando el agente local reporta resultado (vía webhook procesado en backend), el archivo aparece en la lista de anexos del wizard automáticamente.
  - Si el resultado es `incompleta` (atasco de papel), muestra modal con opción "Reintentar" o "Continuar sin este anexo".
- **Contexto activo:** la UI llama `POST /api/v1/gd/perifericos/contexto-activo` al abrir el wizard para que el agente local sepa a qué radicado asociar.
- **Endpoints:** `POST /api/v1/gd/perifericos/{id}/digitalizar`, `POST /api/v1/gd/perifericos/contexto-activo`.
- **Componente nuevo:** `<EscanerStatusIndicator />` con estados: ready / scanning / processing / done / error.
- **Aceptación:** radicador escanea oficio físico durante creación de radicado; el PDF aparece en la lista de anexos sin clicks extra; el OCR se ejecuta en background.

### GD-UI-0091 — Pantalla de digitalización por lote
- **Ruta:** `/gd/ventanilla/digitalizacion/lote`.
- **Rol:** ROL-004, ROL-005. Permiso PERM-PER-007.
- **Flujo:**
  1. Wizard paso 1: seleccionar escáner automático + modo separación (por código de barras / por página / manual) + DPI + observación.
  2. Paso 2: cargar documentos en el escáner físico, presionar "Iniciar lote". Vista muestra páginas digitalizadas en tiempo real (polling sobre `GET /api/v1/gd/perifericos/lotes/{lote_id}`).
  3. Paso 3: revisión del lote — si separación por código de barras: cada documento aparece pre-asociado al radicado detectado; usuario puede confirmar o reasignar. Si separación manual: usuario asocia rangos de páginas a radicados.
  4. Paso 4: finalizar lote → `POST /api/v1/gd/perifericos/lotes/{lote_id}/finalizar`.
- **Componente nuevo:** `<LoteDigitalizacionViewer />` con grid de thumbnails de páginas, selección múltiple, asignación a radicados.
- **Endpoints:** `POST /api/v1/gd/perifericos/{id}/digitalizar-lote`, `GET /api/v1/gd/perifericos/lotes/{lote_id}`, `POST /api/v1/gd/perifericos/lotes/{lote_id}/finalizar`.
- **Validaciones:** páginas no asociadas no permiten finalizar (warning); usuario puede dejarlas pendientes para asociar después (PERM-PER-008).
- **Aceptación:** procesar lote de 50 páginas con códigos intercalados; el sistema separa en 5 documentos correctos; usuario confirma y finaliza; los 5 radicados reciben sus anexos.

### GD-UI-0092 — Modal de reimpresión controlada con motivo
- **Ubicación:** ficha del radicado, sección "Impresiones previas" (lista de `gd.impresion_radicado`).
- **Rol:** ROL-004, ROL-005. Permiso PERM-PER-004.
- **Funcionalidad:**
  - Cada impresión previa muestra botón **"Reimprimir"** que abre modal con:
    - Resumen de la impresión original (fecha, periférico, usuario, número intentos previos).
    - **Campo motivo obligatorio** (textarea, mínimo 10 caracteres).
    - Selector de periférico para la reimpresión.
  - Si `intentos_reimpresion > 3`, modal advierte que requiere aprobación del coordinador y la acción crea una solicitud en lugar de imprimir directamente.
- **Endpoints:** `POST /api/v1/gd/perifericos/{id}/reimprimir-etiqueta`.
- **Componente:** `<MotivoReimpresionModal />`.
- **Aceptación:** reimprimir etiqueta sin motivo falla con feedback inline; reimprimir con motivo válido funciona; al cuarto intento abre flujo de aprobación.

### GD-UI-0093 — Bandeja de "pendientes de asociación" (escaneos huérfanos)
- **Ruta:** `/gd/ventanilla/digitalizacion/pendientes`.
- **Rol:** ROL-004, ROL-005. Permiso PERM-PER-008.
- **Vista:** lista de digitalizaciones con `estado='correcta'` pero sin radicado asociado (típicamente lotes abandonados o digitalizaciones sin contexto activo).
- **Acciones:** asociar a radicado existente (con buscador) o descartar con motivo.
- **Endpoints:** `GET /api/v1/gd/digitalizaciones?estado=pendiente_asociacion`, `POST /api/v1/gd/digitalizaciones/{id}/asociar`, `POST /api/v1/gd/digitalizaciones/{id}/descartar`.
- **Aceptación:** un lote abandonado de ayer aparece en la bandeja; el coordinador asocia los 3 documentos a sus radicados correctos.

### GD-UI-0094 — Dashboard de salud y fallos de periféricos
- **Ruta:** `/gd/admin/perifericos/dashboard`.
- **Rol:** ROL-001, ROL-005, ROL-016. Permiso PERM-PER-011.
- **Vista:**
  - KPIs arriba: periféricos activos / en mantenimiento / con fallos en últimas 24h.
  - Tarjetas por periférico con: estado, número de operaciones del día, número de fallos, latencia promedio, link "Ver historial".
  - Tabla de eventos críticos recientes (`autenticacion_fallida_agente`, fallos consecutivos, periféricos auto-protegidos).
  - Sección "Mantenimientos próximos" con fechas estimadas.
- **Acciones:** programar mantenimiento, marcar mantenimiento finalizado, revocar agente local comprometido (PERM-PER-001).
- **Endpoints:** `GET /api/v1/gd/perifericos/eventos/fallos`, `GET /api/v1/gd/perifericos/{id}/historial`, `POST /api/v1/gd/perifericos/{id}/mantenimiento`, `POST /api/v1/gd/agentes-locales/{id}/revocar`.
- **Aceptación:** el coordinador ve que Counter-2 ha tenido 6 fallos hoy y está en `mantenimiento` automático; agenda mantenimiento correctivo para mañana.

---

## Anexo — Cobertura de Definition of Done por entrega

| Entrega | Épicas UI completadas | Hitos |
|---|---|---|
| Entrega 1 | EP-001 + EP-008 | Login, sidebar por rol, administración base, configuración institucional, estructura orgánica versionada. Habilita Admin Sistema y Admin Seguridad. |
| Entrega 2 | EP-002 + EP-013 | Radicador puede crear radicados de entrada/salida con QR; coordinador supervisa cola; operación presencial con periféricos (impresión etiqueta/constancia + digitalización + bandeja de huérfanos) si la organización lo activa. |
| Entrega 3 | EP-003 + EP-012 | Buzón unificado funcionando para todos los roles operativos; notificaciones y alertas activas. |
| Entrega 4 | EP-004 | Ciclo completo de PQRSD desde clasificación hasta cierre, con semáforo de vencimientos. |
| Entrega 5 | EP-005 | Correspondencia interna y externa con workflow completo. |
| Entrega 6 | EP-006 | Documentos versionados, plantillas operativas, firma electrónica funcional. |
| Entrega 7 | EP-009 + EP-010 + EP-011 | Auditoría visible para el rol Auditor, reportes exportables, IA embebida en flujos, correo institucional en producción. |
| Entrega 8 | EP-007 | TRD/TVD versionadas y clasificación documental atándose a expedientes básicos. |

---

**Última actualización:** 2026-05-23 (rev. EP-013 UI — periféricos)
**Versión:** 0.1 (borrador — pendiente de validación)
