# Módulo Gestión Documental con IA — Plataforma de Ventanilla Única, PQRSD y Correspondencia

> Carpeta **externa** a `docs/BACKLOG.md` y `docs/UI_BACKLOG.md`. Estos backlogs son **independientes** del producto principal (CopilotoIA), no comparten consecutivos ni se ejecutan en el mismo flujo de PRs hasta que el usuario lo indique explícitamente.

## 0. Neutro de sector — público, privado, mixto

Los documentos fuente del cliente fueron escritos para una **entidad pública** y usan terminología legal colombiana (PQRSD con términos hábiles, TRD/TVD, constancia con QR verificable públicamente, Ley 1755). El módulo **conserva esa terminología** porque la documentación lo exige, pero **el producto resultante debe operar en cualquier tipo de organización**: empresa privada, ONG, gremio, cooperativa, entidad mixta y entidad pública. Esto se logra con dos mecanismos:

1. **`gd.perfil_organizacion.tipo_organizacion`** ∈ `{publica, privada, mixta, ong, gremial, cooperativa}` — atributo del perfil 1:1 con el tenant.
2. **`gd.organizacion_modulo_activacion`** — feature flags individuales por organización: `pqrsd_legal`, `pqrsd_tickets`, `correspondencia_interna/externa`, `firma_escaneada/electronica/digital_certificada`, `expedientes`, `trd_tvd`, `consulta_publica_radicado`, `integracion_correo`, `agentes_ia`, `radicacion_externa_desde_dependencia`.

Defaults coherentes por tipo de organización (GD-API-0011.c):
- **Pública**: todo activo, calendario hábil colombiano, TRD obligatoria, consulta pública con QR.
- **Privada**: módulos esenciales (correspondencia + documentos + firma + IA), PQRSD desactivado, TRD opcional.
- **ONG**: como privada + expedientes activos por default.
- **Mixta**: como pública con FAQ guiando al admin qué módulos legales aplican.

El admin puede activar/desactivar cualquier módulo en cualquier momento desde la UI (GD-UI-0052).

## 1. Origen funcional

Los **PDFs originales del cliente** viven anexados al repo bajo [`source-documents/`](source-documents/) (versionados — no se actualizan sin justificación expresa del cliente, ya que una nueva versión obligaría a re-auditar el backlog completo). La auditoría de cobertura tarea por tarea, sección por sección, está en [`TRAZABILIDAD.md`](TRAZABILIDAD.md) y se actualiza cada vez que el cliente publica una nueva versión de algún documento o cuando se añade/elimina una tarea.

Este módulo implementa la plataforma institucional descrita en los cinco documentos fuente entregados por el cliente:

| Doc fuente (archivo en `source-documents/`) | Aporte al backlog |
|---|---|
| [`01-vision-alcance-producto-v0.1.pdf`](source-documents/01-vision-alcance-producto-v0.1.pdf) | Alcance funcional, módulos 1–15, fases, principios funcionales, plantillas, flujos de extremo a extremo. |
| [`02-requisitos-no-funcionales-v0.1.pdf`](source-documents/02-requisitos-no-funcionales-v0.1.pdf) | 60 RNF (RNF-001 a RNF-060) con criterios verificables — cada épica enlaza los RNF que cumple. |
| [`03-matriz-roles-permisos-funciones-v0.1.pdf`](source-documents/03-matriz-roles-permisos-funciones-v0.1.pdf) | 19 roles (ROL-001..ROL-019) + ~140 permisos (PERM-*) + reglas especiales de seguridad. |
| [`04-mapa-modulos-arquitectura-logica-v0.1.pdf`](source-documents/04-mapa-modulos-arquitectura-logica-v0.1.pdf) | 20 módulos (MOD-001..MOD-020) + dependencias + eventos del sistema. |
| [`05-modelo-datos-conceptual-v0.1.pdf`](source-documents/05-modelo-datos-conceptual-v0.1.pdf) | 36 entidades críticas para v1 + reglas de persistencia histórica + estados conceptuales. |
| [`05-modelo-datos-conceptual-v0.1-rev1-perifericos.pdf`](source-documents/05-modelo-datos-conceptual-v0.1-rev1-perifericos.pdf) | **Revisión 1 del Doc 5** entregada 2026-05-23 — agrega § 28 con 5 entidades de periféricos (`Periferico`, `PuntoAtencion`, `ImpresionRadicado`, `DigitalizacionDocumento`, `CodigoBarrasRadicado`) + 10 permisos PERM-PER-001..010. Cubierto por EP-021. |
| [`06-componente-perifericos-v0.1.pdf`](source-documents/06-componente-perifericos-v0.1.pdf) | **Documento técnico especial** entregado 2026-05-23 — define arquitectura agente local / servicio puente / plugin / API fabricante; 8 requisitos funcionales (RFP-001..008) + 6 no funcionales (RNFP-001..006); permisos PERM-PER-011..012; flujos de radicación presencial + escaneo por lote. Cubierto por EP-021 + EP-013 UI. |

Los PDFs originales no se versionan en el repo (vienen del cliente). Cualquier ambigüedad se resuelve por el orden de prelación:

1. Modelo de Datos Conceptual (qué se persiste).
2. Requisitos No Funcionales (cómo debe comportarse).
3. Matriz de Roles (quién puede hacer qué).
4. Mapa de Módulos (cómo se separa el código).
5. Visión y Alcance (qué entra a la versión 1).

## 2. Convenciones de consecutivos

- **Backend / API:** prefijo `GD-API-NNNN` (`BACKLOG.md`). Reservado el rango `GD-API-0001..GD-API-9999`.
- **Frontend / UI:** prefijo `GD-UI-NNNN` (`UI_BACKLOG.md`). Reservado el rango `GD-UI-0001..GD-UI-9999`.
- **Épicas:** `GD-API-EP-NNN` y `GD-UI-EP-NNN`. Sirven para agrupar; no se "ejecutan" sueltas.
- **Bugs:** `GD-BUG-NNNN` (compartido por API/UI). Se crean cuando aparezca el primero.

No reutilizar números: si una tarea se mueve a un futuro `docs/gestion documental/DONE.md`, su consecutivo queda quemado.

## 3. Mandato del módulo (extiende el mandato del producto principal)

1. **Ventanilla Única es el centro.** Todo objeto institucional (PQRSD, correspondencia, documento) nace o se relaciona con un radicado. La API no acepta crear PQRSD sin radicado de entrada asociado, salvo el caso explícito de correo importado (que crea ambos en una transacción).
2. **Radicado inmutable.** Una vez asignado el `numeroRadicado`, no se edita, no se elimina, no se reutiliza. La única operación destructiva es anulación (con flujo de aprobación) y deja el número quemado.
3. **No eliminación física.** Usuarios, dependencias, documentos, TRD/TVD, plantillas, radicados, PQRSD, correspondencia y eventos de auditoría **no exponen DELETE**. Solo inactivar / anular / versionar / cerrar vigencia. Las APIs `DELETE /...` no se implementan; el verbo correcto es `POST /.../anular` o `PATCH ... { estado: 'inactivo' }` con justificación.
4. **Snapshots obligatorios.** Toda actuación (firma, asignación, evento de auditoría, reasignación, cierre) guarda copia del nombre del rol, dependencia y cargo usados en ese momento — no referencias por id que rompan al cambiar la estructura.
5. **IA asistida, no decisoria.** Ningún endpoint de IA escribe directamente en `radicados`, `pqrsd`, `documentos` o `firmas`. La IA devuelve sugerencias persistidas en `solicitud_ia` / `resultado_ia`; un endpoint humano separado las acepta/modifica/rechaza y solo entonces se materializa el cambio.
6. **Auditoría como dominio aparte.** El módulo `Auditoría` escribe a un almacén separado de la base transaccional (mismo motor, distinto schema o tabla `evento_auditoria` particionada). Ningún módulo funcional puede `UPDATE` ni `DELETE` esa tabla; solo `INSERT`.
7. **Versionado de TRD/TVD/plantillas/dependencias bloquea borrado.** Una versión que ya fue usada para clasificar al menos un documento o radicado se cierra (estado `histórica`), nunca se modifica ni elimina.
8. **Permisos validados en backend.** Aunque la UI oculte un menú, cada endpoint valida `usuario → rol → permiso → alcance (propio/dependencia/institucional/global)`. La UI nunca es la fuente de verdad de autorización.
9. **APIs por dominio.** Cada módulo del Mapa de Arquitectura tiene su prefijo de ruta (`/api/v1/gd/ventanilla`, `/api/v1/gd/pqrsd`, `/api/v1/gd/documentos`, etc.). No se mezclan módulos en un mismo router gigante.
10. **Eventos como primer ciudadano.** Cada acción crítica emite un evento de dominio (`RadicadoCreado`, `PQRSDVencida`, `DocumentoFirmado`, etc.) hacia el bus interno. Auditoría, notificaciones y reportes consumen eventos — no leen tablas directamente.
11. **Cero acoplamiento con CopilotoIA principal — con dos excepciones explícitas y justificadas.** Este módulo vive bajo el prefijo `gd_` (schema, tablas, rutas, módulos React). Comparte autenticación e infraestructura, no lógica de negocio del producto comercial. Las **dos zonas transversales** viven en `core.*` (no en `gd.*` ni en `app.*`) y sirven tanto al producto principal como al módulo Knowledge y a Gestión Documental:

    a. **EP-018 — Archivos + extracción + OCR.** `core.archivo_digital` + `core.extraccion_resultado`. Storage de bytes, antivirus, extractores (PDF/DOCX/XLSX/OCR). Reemplaza al storage tenant-scoped que hoy vive en `app/services/knowledge_storage.py`. Sin duplicar backup, sin duplicar antivirus.

    b. **EP-019 — Auditoría transversal.** `core.evento_auditoria` particionada y append-only por trigger. Reemplaza a `app.audit_logs` y absorbe `app.consent_ledger`. Una sola tabla con campo `dominio ∈ {core, app, gd, knowledge}` para diferenciar fuente; permite reconstruir incidentes que cruzan dominios (ej. un mismo usuario que anula una PQRSD y luego exporta un contacto GDPR — dos eventos hoy en tablas distintas, una sola query mañana).

    Los **modelos de dominio** se mantienen separados (`app.knowledge_documents` vs `gd.documento` vs `app.contacts` vs `gd.tercero`). Solo se comparte la capa transversal de **bytes, texto extraído y eventos auditables**. Cualquier excepción adicional debe documentarse aquí con la misma estructura.

12. **Neutro de sector por configuración, no por código.** No existirán dos versiones del módulo "GD para empresa privada" y "GD para entidad pública". Existe **una sola versión** cuyo comportamiento se ajusta por el `tipo_organizacion` del perfil y los módulos activados. Ver sección 0 arriba. Quien escriba `if tipo_organizacion == 'publica':` dentro del código de dominio está violando este mandato; la decisión debe leer de `gd.organizacion_modulo_activacion`.

## 4. Cómo se navega este backlog

- [`BACKLOG.md`](BACKLOG.md) → tareas de **backend / API / base de datos / workers / integraciones / IA**. Agrupadas en **21 épicas** (EP-001..EP-021) alineadas a los 20 módulos (MOD-001..MOD-020) del Mapa de Arquitectura más dos servicios transversales (EP-018 archivos, EP-019 auditoría), una de cierre de gaps (EP-020) y una para **periféricos de Ventanilla Única** (EP-021 — Doc 5-rev1 + Doc 6). Total ≈142 tareas (GD-API-0001..GD-API-0142).
- [`UI_BACKLOG.md`](UI_BACKLOG.md) → tareas de **frontend (admin-panel)** para todos los roles. Agrupadas en **13 épicas** alineadas a los menús por rol que define la Matriz de Roles, incluyendo EP-013 para operación de periféricos. Total ≈94 tareas (GD-UI-0001..GD-UI-0094).
- [`integracion/`](integracion/) → **carpeta de contratos UI ↔ Backend** (nueva, 2026-05-23). Por cada endpoint REST documenta request payload, response (2xx + errores específicos), permisos, eventos emitidos y qué ticket UI lo consume. Organizada por entrega:
  - [`integracion/README.md`](integracion/README.md) — índice maestro + convenciones (errores, paginación, snapshots, headers obligatorios, reglas IA/archivos/anulación).
  - [`integracion/INTEGRACION_E1_IDENTIDAD.md`](integracion/INTEGRACION_E1_IDENTIDAD.md) — EP-001 + EP-002 + EP-019 (~50 endpoints).
  - [`integracion/INTEGRACION_E2_VENTANILLA.md`](integracion/INTEGRACION_E2_VENTANILLA.md) — EP-004 + EP-005 + EP-021 (~45 endpoints, incluye periféricos completos + webhooks del agente local + tabla de mapeo ticket UI ↔ endpoints).
  - Entregas E3 a E8 + RPA: pendientes (siguiente iteración, ver TRAZABILIDAD § 7).
- [`ARQUITECTURA.md`](ARQUITECTURA.md) → cinco mermaids: ER tenant↔perfil↔módulos, arquitectura completa core/app/knowledge/gd, flujo end-to-end de PDF escaneado con OCR, activación de módulos por tipo de organización, patrones de tenancy.
- [`TRAZABILIDAD.md`](TRAZABILIDAD.md) → auditoría cruzada: cada sección de cada PDF (incluidos Doc 5-rev1 y Doc 6) mapeada a la tarea que la cubre, con identificación explícita de gaps (cerrados en EP-020 y EP-021).
- [`source-documents/`](source-documents/) → los **siete PDFs** del cliente versionados en el repo (5 originales + rev1 de Doc 5 + Doc 6 nuevo).

Cada tarea declara:
- **Épica padre.**
- **Módulos del Mapa que toca (MOD-NNN).**
- **Entidades de datos que crea o modifica (Modelo de Datos Conceptual).**
- **RNF que satisface (lista de RNF-NNN).**
- **Permisos que introduce o consume (PERM-*).**
- **Roles afectados (ROL-NNN).**
- **Eventos de dominio emitidos (si aplica).**
- **Criterios de aceptación verificables.**
- **Dependencias hacia otras tareas (`GD-API-NNNN` o `GD-UI-NNNN`).**

## 5. Orden recomendado de entrega

Sigue el plan de 8 entregas del documento de Visión y Alcance (sección 28):

```
Entrega 1 — Base institucional y seguridad
    ├─ Épicas API: EP-001 (Identidad), EP-002 (Configuración + Estructura orgánica), EP-003 (Auditoría base)
    └─ Épicas UI:  EP-001 (Design system + routing), EP-008 (Administración)

Entrega 2 — Ventanilla Única (con periféricos opcionales)
    ├─ Épicas API: EP-004 (Ventanilla + Radicación), EP-005 (Terceros), EP-021 (Periféricos — opcional)
    └─ Épicas UI:  EP-002 (Ventanilla Única), EP-013 (Periféricos — opcional)
    └─ Nota: EP-021 / EP-013 solo se activan si la organización marca
       `ventanilla_presencial_con_perifericos=true` (default sí para tipo_organizacion='publica'
       o 'mixta', no para 'privada' que opera solo digital).

Entrega 3 — Buzón y tareas
    ├─ Épicas API: EP-006 (Buzón + Tareas + Notificaciones + Alertas)
    └─ Épicas UI:  EP-003 (Buzón de trabajo), EP-012 (Notificaciones)

Entrega 4 — PQRSD
    ├─ Épicas API: EP-007 (PQRSD ciclo completo)
    └─ Épicas UI:  EP-004 (PQRSD)

Entrega 5 — Correspondencia
    ├─ Épicas API: EP-008 (Correspondencia)
    └─ Épicas UI:  EP-005 (Correspondencia)

Entrega 6 — Documentos y plantillas
    ├─ Épicas API: EP-009 (Documentos), EP-010 (Plantillas), EP-011 (Firmas)
    └─ Épicas UI:  EP-006 (Documentos + plantillas + firmas)

Entrega 7 — Correo, IA, reportes
    ├─ Épicas API: EP-012 (Correo), EP-013 (IA), EP-014 (Reportes)
    └─ Épicas UI:  EP-010 (IA asistida en flujos), EP-011 (Correo), EP-009 (Reportes + auditor)

Entrega 8 — TRD/TVD base
    ├─ Épicas API: EP-015 (TRD/TVD/clasificación), EP-016 (Expediente básico)
    └─ Épicas UI:  EP-007 (TRD/TVD + clasificación)

Futuro — RPA
    └─ Épica API:  EP-017 (preparación RPA)
```

No avanzar a una Entrega sin completar la anterior: la dependencia de datos es real (no se puede crear una PQRSD sin Ventanilla Única, no se puede asignar a un funcionario sin Usuarios + Dependencias, etc.).

## 6. Definition of Done por tarea

Toda tarea (`GD-API-NNNN` o `GD-UI-NNNN`) se considera terminada solo si:

1. Código y migraciones mergeados en `main`.
2. Tests automatizados que cubren el camino feliz y al menos un caso de error (autorización denegada, validación, conflicto de estado).
3. Endpoint documentado en OpenAPI (para `GD-API-*`) o storybook/screenshot (para `GD-UI-*`).
4. Eventos de auditoría verificados con un test que ejecute la acción y consulte `evento_auditoria`.
5. Permisos validados con un test por rol relevante (al menos un test "rol permitido pasa" y "rol no permitido recibe 403").
6. Si la tarea introduce una nueva entidad: incluida en el diagrama ER (archivo `docs/gestion documental/ERD.md` — se crea con la primera entidad).
7. Si la tarea afecta la Matriz de Roles: actualizada `docs/gestion documental/MATRIZ_PERMISOS.md` (se crea con `GD-API-0010`).

## 7. Lo que NO está aquí (delegado a documentos del cliente)

- Decisión final de stack tecnológico → cliente.
- Cronograma con fechas → cliente.
- Estimaciones en horas → equipo de desarrollo.
- Modelo físico de base de datos → derivado del Modelo Conceptual, se diseña en la primera tarea de cada épica que toca una entidad nueva.

---

**Última actualización:** 2026-05-23 (rev. EP-021 — periféricos + carpeta `integracion/`)
**Versión:** 0.1.1 (revisión incremental — incorpora Doc 5-rev1 y Doc 6 entregados por el cliente; pendiente de validación final por el cliente antes de iniciar ejecución de EP-021)
