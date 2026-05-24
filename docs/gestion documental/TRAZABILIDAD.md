# Matriz de trazabilidad — Requisito → Tarea del backlog

> Para cada sección de cada uno de los 5 documentos fuente del cliente (en `source-documents/`), este archivo lista qué tarea del backlog (`BACKLOG.md` o `UI_BACKLOG.md`) la implementa. Si una celda dice **GAP**, el backlog no cubre ese requisito y la sección 6 al final detalla la corrección añadida.
>
> Convención de citas: `Doc N § X.Y` donde:
> - **Doc 1** = `01-vision-alcance-producto-v0.1.pdf` (Visión y Alcance del Producto)
> - **Doc 2** = `02-requisitos-no-funcionales-v0.1.pdf` (Requisitos No Funcionales)
> - **Doc 3** = `03-matriz-roles-permisos-funciones-v0.1.pdf` (Matriz de Roles, Permisos y Funciones)
> - **Doc 4** = `04-mapa-modulos-arquitectura-logica-v0.1.pdf` (Mapa de Módulos y Arquitectura Lógica)
> - **Doc 5** = `05-modelo-datos-conceptual-v0.1.pdf` (Modelo de Datos Conceptual)
> - **Doc 5-rev1** = `05-modelo-datos-conceptual-v0.1-rev1-perifericos.pdf` (Modelo de Datos Conceptual — **revisión 1**, agrega § 28 sobre interacción con periféricos: nuevas entidades `Periferico`, `PuntoAtencion`, `ImpresionRadicado`, `DigitalizacionDocumento`, `CodigoBarrasRadicado` + permisos PERM-PER-001..010)
> - **Doc 6** = `06-componente-perifericos-v0.1.pdf` (Documento Técnico Especial — Componente de Comunicación con Periféricos para Ventanilla Única — define arquitectura agente local/servicio puente/plugin navegador, RFP-001..008, RNFP-001..006, permisos PERM-PER-011..012, entidad `EventoPeriferico`)

---

## 1. Doc 1 — Visión y Alcance del Producto

### 1.1 Objetivos específicos (Doc 1 § 5)

| # | Objetivo específico | Tarea(s) backlog |
|---|---|---|
| 1 | Centralizar recepción por Ventanilla Única | GD-API-0024..0026 |
| 2 | Generar radicados únicos, trazables, inalterables | GD-API-0023, 0024 |
| 3 | Clasificar radicados (PQRSD/correspondencia/trámite/expediente) | GD-API-0026, 0027 |
| 4 | Control de términos legales y alertas PQRSD | GD-API-0041, 0042 |
| 5 | Asignar a dependencias y funcionarios | GD-API-0044, 0045 |
| 6 | Buzón de trabajo por usuario | GD-API-0038, 0039 |
| 7 | Correspondencia interna y externa | GD-API-0052..0056 |
| 8 | Generar documentos base desde plantillas | GD-API-0064..0067 |
| 9 | Control de versiones documentos | GD-API-0059, 0062 |
| 10 | Firma electrónica/digital/escaneada | GD-API-0068..0072 |
| 11 | Integrar buzones de correo institucional | GD-API-0073..0076 |
| 12 | Agentes IA (clasificación, extracción, resumen, duplicados, borrador) | GD-API-0077..0086 |
| 13 | Auditoría completa | GD-API-0115..0121 (EP-019) |
| 14 | Usuarios OPS/temporales sin pérdida histórica | GD-API-0003, 0008 |
| 15 | Preparación TRD, TVD, expedientes, SGDEA | GD-API-0095..0104 |
| 16 | Reportes e indicadores de gestión | GD-API-0087..0094 |
| 17 | Reducir uso de papel (cero papel progresivo) | Transversal — todas las épicas |

**Cobertura:** 17/17 ✓

### 1.2 Principios funcionales (Doc 1 § 6)

| Principio | Tarea / mandato |
|---|---|
| 6.1 Ventanilla Única como entrada principal | Mandato README #1 + GD-API-0024..0032 |
| 6.2 Radicado único e inalterable | Mandato README #2 + GD-API-0023 |
| 6.3 Buzón institucional por usuario | GD-API-0038, 0039 |
| 6.4 Roles configurables | GD-API-0004 (no quemados en código) |
| 6.5 Gestión documental desde el inicio | EP-015, EP-016 desde primera versión |
| 6.6 No eliminación histórica | Mandato README #3 + triggers en GD-API-0001, 0017 (EP-019), 0115 |
| 6.7 IA asistida, no decisoria | Mandato README #5 + GD-API-0084 (decisión humana obligatoria) |
| 6.8 Cero papel progresivo | Implícito en todo el módulo (anexos digitales, plantillas, firmas) |

**Cobertura:** 8/8 ✓

### 1.3 Usuarios objetivo (Doc 1 § 7)

| Tipo de usuario interno | Rol del backlog (Doc 3 § 7) |
|---|---|
| Radicadores VU | ROL-004 |
| Coordinadores VU | ROL-005 |
| Administradores PQRSD | ROL-006 |
| Jefes de dependencia | ROL-009 |
| Secretarios de dependencia | ROL-010 |
| Profesionales responsables | ROL-007 |
| Revisores jurídicos/técnicos | ROL-008 |
| Firmantes autorizados | ROL-014 |
| Administradores documentales | ROL-003 |
| Administradores del sistema | ROL-001 |
| Auditores internos | ROL-016 |
| Usuarios de consulta | ROL-015 |
| Contratistas OPS | `tipo_vinculacion='ops'` en `gd.perfil_usuario` (GD-API-0001) |
| Usuarios temporales | `tipo_vinculacion='provisional|supernumerario|practicante'` |

Usuarios externos futuros (Doc 1 § 7.2): cubiertos por mandato "fuera de v1" + Fase 3 portal ciudadano (Doc 1 § 10).

**Cobertura:** 14/14 internos ✓ + externos = fase 3 ✓

### 1.4 Módulos primera versión (Doc 1 § 8.1)

| Módulo Doc 1 | Épica backlog | Mapeo MOD del Doc 4 |
|---|---|---|
| Módulo 1 — Configuración institucional | EP-002 | MOD-002 |
| Módulo 2 — Usuarios, roles y permisos | EP-001 | MOD-001 |
| Módulo 3 — Ventanilla Única | EP-004 | MOD-004 |
| Módulo 4 — PQRSD | EP-007 | MOD-007 |
| Módulo 5 — Correspondencia externa recibida | EP-008 | MOD-008 |
| Módulo 6 — Correspondencia externa enviada | EP-008 | MOD-008 |
| Módulo 7 — Correspondencia interna | EP-008 | MOD-008 |
| Módulo 8 — Buzón de trabajo | EP-006 | MOD-009 |
| Módulo 9 — Documentos, anexos y plantillas | EP-009, EP-010 | MOD-010, MOD-011 |
| Módulo 10 — Firmas | EP-011 | MOD-012 |
| Módulo 11 — Integración correo | EP-012 | MOD-018 |
| Módulo 12 — IA asistida básica | EP-013 | MOD-019 |
| Módulo 13 — Auditoría y trazabilidad | EP-019 (transversal) | MOD-016 |
| Módulo 14 — Reportes e indicadores | EP-014 | MOD-017 |
| Módulo 15 — Preparación TRD/TVD | EP-015 | MOD-013 |

**Cobertura:** 15/15 ✓

### 1.5 Flujos principales (Doc 1 § 12)

| Flujo | Tareas backlog |
|---|---|
| 12.1 Radicación de entrada | GD-API-0024 + GD-API-0026 + GD-UI-0007 |
| 12.2 Flujo PQRSD completo (13 pasos) | GD-API-0043..0048 + GD-UI-0020..0028 |
| 12.3 Correspondencia externa recibida | GD-API-0053 + GD-UI-0030 |
| 12.4 Correspondencia externa enviada (10 pasos) | GD-API-0054 + GD-UI-0031..0033 |
| 12.5 Correspondencia interna | GD-API-0052 + GD-UI-0029, 0030 |
| 12.6 Usuario OPS finalizado (8 pasos) | GD-API-0003 + GD-API-0008 + GD-UI-0019 |
| 12.7 Generación documento base (8 pasos) | GD-API-0065 + GD-UI-0023 |

**Cobertura:** 7/7 ✓

### 1.6 Reglas de negocio de alto nivel (Doc 1 § 16) — 20 reglas

| # | Regla | Implementación |
|---|---|---|
| 1 | Radicado oficial con número único | GD-API-0023 (consecutivo transaccional) |
| 2 | Ventanilla Única entrada principal | Mandato README #1 |
| 3 | Usuario solo ve/actúa según rol+dependencia | GD-API-0006 (middleware) |
| 4 | Roles configurables | GD-API-0004 |
| 5 | Permisos limitables por dependencia | GD-API-0005 + `gd.asignacion_alcance` |
| 6 | Actuaciones históricas no se alteran | GD-API-0009 (snapshots) + EP-019 append-only |
| 7 | Usuarios inactivos no ingresan | GD-API-0002 + GD-API-0003 |
| 8 | Tareas de usuarios inactivos reasignables | GD-API-0008 |
| 9 | Radicados no se eliminan; se anulan | GD-API-0028 |
| 10 | Documentos no se sobrescriben; se versionan | GD-API-0059 + GD-API-0062 |
| 11 | Respuesta oficial requiere revisión+aprobación+firma | GD-API-0047 |
| 12 | IA sugiere, no decide | GD-API-0084 + mandato #5 |
| 13 | Firmas con asociación a usuario/cargo/dep/fecha | GD-API-0069 (snapshots de firma) |
| 14 | Plantillas con versión y vigencia | GD-API-0064 |
| 15 | TRD/TVD versionadas | GD-API-0095, 0096 |
| 16 | Dependencias conservan historial | GD-API-0012 (estructura versionada) |
| 17 | Correos importados conservan evidencia | GD-API-0074 (preserva message_id + correo original) |
| 18 | Anexos asociados a radicado/expediente | GD-API-0060 (polimórfico) |
| 19 | Acciones críticas auditadas | EP-019 completo |
| 20 | Información sensible con control reforzado | GD-API-0063 + RNF-053 |

**Cobertura:** 20/20 ✓

### 1.7 Estados principales (Doc 1 § 15)

| Estado | Definido en |
|---|---|
| Radicado: registrado/clasificado/derivado/en gestión/respondido/cerrado/anulado | GD-API-0001 + GD-API-0024 |
| PQRSD: 14 estados (nueva..anulada) | GD-API-0001 + GD-API-0043 |
| Documento: 10 estados | GD-API-0059 |
| Usuario: 5 estados | `gd.perfil_usuario.estado_gd` (GD-API-0001) |

**Cobertura:** 4/4 grupos de estados ✓

### 1.8 Plantillas documentales seed (Doc 1 § 19.1) — 7 plantillas

| Plantilla | Cobertura |
|---|---|
| Oficio de respuesta | GD-API-0067 (seed) |
| Memorando interno | GD-API-0067 |
| Constancia de radicación | GD-API-0067 + GD-API-0030 |
| Traslado por competencia | GD-API-0067 + GD-API-0049 |
| Solicitud de información adicional | GD-API-0067 + GD-API-0050 |
| Respuesta a PQRSD | GD-API-0067 + GD-API-0046 |
| Comunicación externa de salida | GD-API-0067 + GD-API-0054 |

**Cobertura:** 7/7 ✓

### 1.9 Indicadores iniciales (Doc 1 § 23) — 13 indicadores

| Indicador | Tarea |
|---|---|
| Radicados creados / por canal | GD-API-0087 |
| PQRSD recibidas / por tipo / vencidas / próximas / tiempo promedio | GD-API-0088 + GD-API-0051 |
| Correspondencia interna/externa | GD-API-0089 |
| Tareas pendientes | GD-API-0090 |
| Documentos generados por plantilla | GD-API-0091 |
| Reasignaciones / Anulaciones | GD-API-0092 |
| Uso de IA | GD-API-0091 |
| Usuarios activos/inactivos | GD-API-0090 |

**Cobertura:** 13/13 ✓

### 1.10 Supuestos iniciales (Doc 1 § 25) — 10 supuestos

Estos son supuestos del cliente, no requisitos. Se documentan en el README sección 1 (origen funcional) y no requieren tareas.

### 1.11 Dependencias funcionales (Doc 1 § 26) — 18 ítems

Son datos previos al desarrollo (estructura orgánica, listado dependencias, cargos, roles iniciales, etc.). Cubiertos por las tareas de seed/configuración: GD-API-0011, 0012, 0013, 0014, 0015, 0064, 0067, 0095, 0073.

---

## 2. Doc 2 — Requisitos No Funcionales

Ver **Anexo B del BACKLOG.md** — todos los 60 RNF están mapeados. Cobertura **60/60** ✓.

### 2.1 Principios rectores de arquitectura (Doc 2 § 3) — 10 principios

| # | Principio | Mandato/tarea |
|---|---|---|
| 1 | Ventanilla Única como entrada | Mandato #1 |
| 2 | Radicado único, trazable, inalterable | Mandato #2 |
| 3 | No eliminación lógica | Mandato #3 |
| 4 | Historial institucional permanente | Mandato #4 (snapshots) |
| 5 | Seguridad desde el diseño | EP-001 + EP-019 |
| 6 | Gestión documental progresiva | EP-015, EP-016 |
| 7 | IA asistida, no decisoria | Mandato #5 |
| 8 | Interoperabilidad futura | EP-017 |
| 9 | Trazabilidad completa | EP-019 |
| 10 | Cero papel progresivo | Implícito |

**Cobertura:** 10/10 ✓

### 2.2 Requisitos críticos para v1 (Doc 2 § 7) — 20 ítems

Todos cubiertos en EP-001..EP-019 según el plan de 8 entregas del README §5.

---

## 3. Doc 3 — Matriz de Roles, Permisos y Funciones

### 3.1 Estados del usuario (Doc 3 § 4) — 5 estados

`gd.perfil_usuario.estado_gd ∈ {activo, suspendido, inactivo, bloqueado, retirado}` (GD-API-0001) ✓

### 3.2 Tipos de vinculación (Doc 3 § 5) — 7 tipos

`gd.perfil_usuario.tipo_vinculacion ∈ {planta, provisional, ops, supernumerario, practicante, externo_autorizado, administrador_tecnico}` (GD-API-0001) ✓

### 3.3 Alcances de permisos (Doc 3 § 6) — 6 alcances

`gd.asignacion_alcance.alcance ∈ {propio, dependencia, dependencias_autorizadas, institucional, global, solo_consulta}` (GD-API-0005) ✓

### 3.4 Roles base (Doc 3 § 7) — 19 roles ROL-001..ROL-019

Todos seedeados en GD-API-0001 (matriz `gd.rol`). Cobertura **19/19** ✓.

### 3.5 Catálogo de permisos (Doc 3 § 8) — ~140 permisos

Todas las 15 subsecciones cubiertas en GD-API-0001 seed (`gd.permiso`):

| Sección | Categoría | Cobertura |
|---|---|---|
| 8.1 | Administración usuarios (PERM-USR-001..012) | GD-API-0003 |
| 8.2 | Roles y funciones (PERM-ROL-001..007) | GD-API-0004 |
| 8.3 | Ventanilla Única (PERM-VU-001..020) | GD-API-0024..0032 |
| 8.4 | PQRSD (PERM-PQRSD-001..025) | GD-API-0043..0051 |
| 8.5 | Correspondencia interna (PERM-CI-001..010) | GD-API-0052 |
| 8.6 | Correspondencia externa (PERM-CE-001..013) | GD-API-0053, 0054 |
| 8.7 | Documentos y anexos (PERM-DOC-001..015) | GD-API-0057..0063 |
| 8.8 | Plantillas (PERM-PLA-001..009) | GD-API-0064..0066 |
| 8.9 | Firmas (PERM-FIR-001..007) | GD-API-0068..0072 |
| 8.10 | TRD/TVD (PERM-TRD-001..013) | GD-API-0095..0100 |
| 8.11 | Reportes (PERM-REP-001..009) | GD-API-0087..0094 |
| 8.12 | Auditoría (PERM-AUD-001..008) | GD-API-0119 |
| 8.13 | IA (PERM-IA-001..009) | GD-API-0078..0085 |
| 8.14 | Correo (PERM-COR-001..009) | GD-API-0073..0076 |
| 8.15 | Notificaciones (PERM-NOT-001..007) | GD-API-0040, 0041 |

**Cobertura:** 15/15 categorías ✓

### 3.6 Menús por rol (Doc 3 § 10) — 7 menús

Cubiertos en `UI_BACKLOG.md` sección 3 (mapping rol → landing → sidebar) y épicas GD-UI-EP-002..EP-009.

### 3.7 Reglas especiales (Doc 3 § 11) — 6 reglas

| # | Regla | Tarea |
|---|---|---|
| 11.1 | Anulación radicado con flujo aprobación | GD-API-0028 |
| 11.2 | Inactivación usuario OPS | GD-API-0003 + GD-API-0008 |
| 11.3 | Reglas de firma | GD-API-0069 |
| 11.4 | Generación documento base | GD-API-0065 |
| 11.5 | IA asistida | GD-API-0084 |
| 11.6 | Consulta sensible | GD-API-0061 + GD-API-0119 |

**Cobertura:** 6/6 ✓

### 3.8 Acciones críticas siempre auditadas (Doc 3 § 13) — 22 acciones

Todas las 22 declaradas en EP-019 GD-API-0120 (catálogo formal de eventos). Cobertura **22/22** ✓.

### 3.9 Historias de usuario derivadas (Doc 3 § 15) — 24 historias

Las 24 historias se traducen a tareas concretas:

| # | Historia | Tarea(s) |
|---|---|---|
| 1 | Crear usuario | GD-API-0003 |
| 2 | Asignar rol a usuario | GD-API-0005 |
| 3 | Inactivar usuario OPS | GD-API-0003 + GD-API-0008 |
| 4 | Reasignar tareas usuario inactivo | GD-API-0008 + GD-UI-0019 |
| 5 | Crear rol | GD-API-0004 |
| 6 | Asignar funciones a rol | GD-API-0004 |
| 7 | Crear radicado desde ventanilla | GD-API-0024 + GD-UI-0007 |
| 8 | Clasificar radicado | GD-API-0026 + GD-UI-0009 |
| 9 | Derivar radicado | GD-API-0026 |
| 10 | Consultar buzón usuario | GD-API-0038 + GD-UI-0016 |
| 11 | Consultar buzón dependencia | GD-API-0039 + GD-UI-0017 |
| 12 | Asignar PQRSD | GD-API-0044 + GD-UI-0021 |
| 13 | Proyectar respuesta | GD-API-0046 + GD-UI-0023 |
| 14 | Revisar respuesta | GD-API-0047 + GD-UI-0024 |
| 15 | Aprobar respuesta | GD-API-0047 + GD-UI-0024 |
| 16 | Firmar documento | GD-API-0069 + GD-UI-0041 |
| 17 | Solicitar radicación externa | GD-API-0054 + GD-UI-0031 |
| 18 | Generar documento base | GD-API-0065 + GD-UI-0040 |
| 19 | Solicitar anulación | GD-API-0028 + GD-UI-0011 |
| 20 | Aprobar anulación | GD-API-0028 + GD-UI-0011 |
| 21 | Versionar TRD/TVD | GD-API-0095, 0096 + GD-UI-0045, 0046 |
| 22 | Consultar auditoría | GD-API-0119 + GD-UI-0067 |
| 23 | Usar IA para clasificación sugerida | GD-API-0078 + GD-UI-0073 |
| 24 | Importar correo como radicado | GD-API-0075 + GD-UI-0080 |

**Cobertura:** 24/24 ✓

---

## 4. Doc 4 — Mapa de Módulos y Arquitectura Lógica

### 4.1 Módulos MOD-001..MOD-020

Cobertura completa via épicas EP-001..EP-019. Ver columna "Módulos del Mapa" en índice de épicas del BACKLOG.md.

### 4.2 Eventos principales (Doc 4 § 7) — ~30 eventos

Catálogo formal en GD-API-0120 (`docs/gestion documental/EVENTOS_AUDITORIA.md`) cubre los 6 grupos de eventos (radicación, PQRSD, correspondencia, documentos, usuarios/seguridad, IA). Ver Anexo A del BACKLOG.md.

### 4.3 Capas lógicas (Doc 4 § 4)

- Presentación → `admin-panel/src/features/gd/` (UI_BACKLOG.md EP-001..EP-012).
- API y aplicación → routers `app/api/v1/gd/*` (BACKLOG.md transversal).
- Dominio → `app/domain/gd/` (decisión técnica de implementación).
- Infraestructura → `app/core/files/`, `app/core/audit/`, `app/core/extraction/` (EP-018, EP-019).
- Seguridad transversal → EP-001 + middleware GD-API-0006.

### 4.4 Vista de flujos end-to-end (Doc 4 § 12) — 4 casos

| Caso | Implementación |
|---|---|
| 12.1 PQRSD por correo | GD-API-0075 + GD-API-0078 + GD-API-0083 (chain end-to-end documentada en ARQUITECTURA.md mermaid 3) |
| 12.2 Oficio externo presencial | GD-API-0024 + 0026 + 0053 |
| 12.3 Comunicación interna | GD-API-0052 |
| 12.4 Finalización contrato OPS | GD-API-0003 + 0008 |

**Cobertura:** 4/4 ✓

### 4.5 Límites entre módulos (Doc 4 § 13)

Cubiertos por la separación de épicas y mandato #10 (APIs por dominio).

---

## 5. Doc 5 — Modelo de Datos Conceptual

### 5.1 Entidades críticas v1 (Doc 5 § 25) — 36 entidades

| # | Entidad | Tarea backlog |
|---|---|---|
| 1 | EntidadPublica | → `gd.perfil_organizacion` (GD-API-0011) — neutro de sector |
| 2 | Dependencia | GD-API-0012 |
| 3 | Usuario | → `app.users` + `gd.perfil_usuario` (GD-API-0001) — reutilizado |
| 4 | Rol | GD-API-0001 (`gd.rol` catálogo) |
| 5 | Permiso | GD-API-0001 (`gd.permiso` catálogo) |
| 6 | UsuarioRol | → `app.user_tenant_roles` + `gd.asignacion_alcance` (GD-API-0005) |
| 7 | UsuarioDependencia | → `gd.perfil_usuario.dependencia_actual_id` (GD-API-0001) |
| 8 | Radicado | GD-API-0024 |
| 9 | ConsecutivoRadicacion | GD-API-0023 |
| 10 | Canal | GD-API-0014 |
| 11 | Tercero | GD-API-0033 |
| 12 | PQRSD | GD-API-0043 |
| 13 | TipoPQRSD | GD-API-0014 |
| 14 | AsignacionPQRSD | GD-API-0044, 0045 |
| 15 | Correspondencia | GD-API-0052..0054 |
| 16 | Tarea | GD-API-0036 |
| 17 | Notificacion | GD-API-0040 |
| 18 | Alerta | GD-API-0041 |
| 19 | Documento | GD-API-0059 |
| 20 | VersionDocumento | GD-API-0059 |
| 21 | ArchivoDigital | → `core.archivo_digital` (GD-API-0110) — transversal |
| 22 | Anexo | GD-API-0060 |
| 23 | PlantillaDocumental | GD-API-0064 |
| 24 | VersionPlantilla | GD-API-0064 |
| 25 | FirmaDocumento | GD-API-0069 |
| 26 | TRD | GD-API-0095 |
| 27 | VersionTRD | GD-API-0095 |
| 28 | SerieDocumental | GD-API-0095 |
| 29 | SubserieDocumental | GD-API-0095 |
| 30 | TipoDocumental | GD-API-0095 |
| 31 | ClasificacionDocumental | GD-API-0098 |
| 32 | EventoAuditoria | → `core.evento_auditoria` (GD-API-0115) — transversal |
| 33 | BuzonCorreoInstitucional | GD-API-0073 |
| 34 | CorreoImportado | GD-API-0074 |
| 35 | SolicitudIA | GD-API-0077 |
| 36 | ResultadoIA | GD-API-0077 |

**Cobertura:** 36/36 ✓

### 5.2 Principios del modelo (Doc 5 § 2) — 10 principios

Todos cubiertos por mandatos del README (#1..#12) y reglas obligatorias de las tareas DDL.

### 5.3 Reglas de persistencia histórica (Doc 5 § 23)

Cubiertas por triggers append-only (EP-019), snapshots (GD-API-0009), versionado (GD-API-0059), no-DELETE en UI (mandato UI #8).

### 5.4 Recomendaciones de diseño lógico (Doc 5 § 26) — 15 ítems

| # | Recomendación | Implementado en |
|---|---|---|
| 1 | IDs internos únicos no dependientes del número de radicado | UUID PK en todas las tablas |
| 2 | Número radicado = dato único de negocio | GD-API-0023 |
| 3 | Separar documento de archivo digital | GD-API-0059 ↔ GD-API-0110 |
| 4 | Separar documento de versión documental | GD-API-0059 |
| 5 | Separar usuario de dependencia histórica | `gd.perfil_usuario` + `gd.asignacion_alcance` |
| 6 | Separar rol de permiso | `gd.rol` + `gd.permiso` + `gd.rol_permiso` |
| 7 | Catálogos controlados en lugar de texto libre | Tablas `gd.canal`, `gd.tipo_pqrsd`, etc. |
| 8 | Estados formales con transiciones controladas | RNF-042 + enums tipados |
| 9 | Tablas históricas para dependencias/roles/TRD/TVD | GD-API-0012, 0095, 0096 |
| 10 | Snapshots en auditoría | GD-API-0115 |
| 11 | Índices para campos frecuentes | DDL de cada tarea |
| 12 | Búsqueda documental desde el inicio | GD-API-0029 (radicados), 0098 (clasificación) |
| 13 | Clasificación información sensible | GD-API-0063 |
| 14 | Evitar borrados físicos | Mandato #3 + triggers |
| 15 | Migraciones futuras expediente | EP-016 |

**Cobertura:** 15/15 ✓

---

## 6. GAPS identificados y corregidos

Durante esta auditoría se detectaron **7 gaps** que se añaden al backlog como tareas nuevas:

### 6.1 GAP-1 — Verificación de constancia con QR sin autenticación
- **Origen:** Doc 1 § 6.1 + RNF-011 ("verificación de radicado mediante código de verificación o QR") + Doc 1 § 19.1 (plantilla "Constancia de radicación").
- **Estado actual:** parcialmente en GD-API-0030, pero falta la **página pública sin login** que escanea el QR y muestra estado.
- **Corrección:** GD-API-0122 (ver sección de gaps al final del BACKLOG.md).

### 6.2 GAP-2 — Tipos de documento de identificación configurables (no solo CC/CE/NIT colombianos)
- **Origen:** Doc 5 § 9.1 (`Tercero.tipo_documento ∈ {CC, CE, NIT, pasaporte, otro}`) — restringido a Colombia.
- **Estado actual:** GD-API-0033 menciona el campo pero no su carácter configurable por organización.
- **Corrección:** GD-API-0123 — catálogo de tipos de documento por país/organización.

### 6.3 GAP-3 — Tablas históricas de dependencias-padre (jerarquía versionada)
- **Origen:** Doc 5 § 6.1 + Doc 4 MOD-003 (estructura orgánica versionada incluye relación padre-hijo histórica).
- **Estado actual:** GD-API-0012 menciona `dependencia_padre_id` pero no documenta cómo se versiona la jerarquía completa cuando hay fusiones/divisiones.
- **Corrección:** GD-API-0124 — tabla `gd.relacion_dependencia_historica` para fusiones/divisiones documentadas.

### 6.4 GAP-4 — Política de contraseñas + reuso histórico ✅ CERRADO 2026-05-23 (bloque 2)
- **Origen:** RNF-005 ("política de complejidad", "bloqueo o protección ante intentos fallidos").
- **Estado actual:** GD-API-0007 menciona la tabla pero no especifica el **historial de las últimas N contraseñas**.
- **Corrección:** ajuste a GD-API-0007 — agregar tabla `gd.historico_contrasena(user_id, hash, creada_en)` con política de no-reuso.
- **Implementación final:** `infra/postgres/04-gd-schema.sql` § 3 crea `gd.politica_contrasena` (versionable, una activa por tenant), `gd.historico_contrasena` (append-only por trigger) y `gd.proveedor_identidad_externo` (stub SSO). Endpoints `GET/PATCH /api/v1/gd/seguridad/politica` (PERM-USR-001). Helper `app/gd/services/politica_contrasena.py` con `validar_contrasena_contra_politica()`, `registrar_hash_historico()`, `listar_hashes_recientes()` para que el flujo de change-password del producto principal pueda validar no-reuso contra los últimos N. **Política versionada** (cada PATCH crea nueva fila y marca la anterior como reemplazada, RNF-009).

### 6.5 GAP-5 — Procedimiento de contingencia para radicación manual ante caída del sistema
- **Origen:** RNF-002 ("Deben existir procedimientos de contingencia para radicación manual en caso de caída del sistema").
- **Estado actual:** RNF-002 listado en cobertura pero sin tarea concreta.
- **Corrección:** GD-API-0125 — endpoint `POST /api/v1/gd/ventanilla/radicados/contingencia` que permite ingresar radicados manuales con timestamp diferido y justificación.

### 6.6 GAP-6 — Hoja de control e índice electrónico del expediente (preparación)
- **Origen:** Doc 5 § 17 + RNF-060 ("La estructura deberá permitir hoja de control o índice electrónico en versiones futuras").
- **Estado actual:** EP-016 menciona "futuro" pero el cliente exige que la **estructura quede preparada en v1**.
- **Corrección:** GD-API-0126 — DDL preparatorio `gd.expediente_indice_electronico` (vacío en v1, listo para fase 2).

### 6.7 GAP-7 — Suspensión / reanudación de términos PQRSD con eventos formales
- **Origen:** RNF-023 ("Debe permitir registrar suspensiones, requerimientos o eventos que afecten el término").
- **Estado actual:** GD-API-0042 menciona la suspensión pero sin endpoint formal de reanudación.
- **Corrección:** GD-API-0127 — endpoints separados para suspender, reanudar y consultar historial de eventos de término.

---

## 6.b GAPs cerrados tras revisión 2026-05-23 (Doc 5-rev1 + Doc 6 — Periféricos)

El cliente entregó dos documentos nuevos que introducen una capa operativa completa de interacción con hardware físico en Ventanilla Única. La auditoría detectó **cobertura 0%** en el backlog v0.1 previo — toda la funcionalidad quedaba implícita en menciones de "constancia con QR" sin entidad ni endpoint que la soportara.

### 6.b.1 GAP-8 — Registro de hardware (impresoras, escáneres, lectores)
- **Origen:** Doc 5-rev1 § 28.1 (`Periferico`) + Doc 6 § 7 RFP-001.
- **Estado v0.1:** entidad y endpoints inexistentes.
- **Corrección:** **GD-API-0128** (DDL completo de 6 entidades), **GD-API-0129** (CRUD periféricos).

### 6.b.2 GAP-9 — Puntos de atención presenciales
- **Origen:** Doc 5-rev1 § 28.2 (`PuntoAtencion`).
- **Estado v0.1:** sin entidad — los radicados presenciales no podían declarar dónde se generaron físicamente.
- **Corrección:** **GD-API-0130** (CRUD puntos de atención) + extensión de `gd.radicado` y `gd.canal` para registrar el punto físico.

### 6.b.3 GAP-10 — Códigos de barras y QR institucionales por radicado
- **Origen:** Doc 5-rev1 § 28.5 + Doc 6 § 14 (regla absoluta: no datos sensibles).
- **Estado v0.1:** GD-API-0030 generaba "código de verificación" textual pero no imagen de QR/código barras lista para impresión.
- **Corrección:** **GD-API-0131** — generación de imagen + token opaco verificable. Linter en CI verifica RNF-017 (sin datos personales en el código).

### 6.b.4 GAP-11 — Impresión auditada de etiquetas y constancias
- **Origen:** Doc 5-rev1 § 28.3 + Doc 6 RFP-002, RFP-003, RFP-004.
- **Estado v0.1:** no había contrato con hardware ni registro de impresiones.
- **Corrección:** **GD-API-0132** (etiqueta), **GD-API-0133** (reimpresión controlada con motivo y aprobación al cuarto intento), **GD-API-0134** (constancia formal con plantilla institucional).

### 6.b.5 GAP-12 — Digitalización con trazabilidad (individual y por lote)
- **Origen:** Doc 5-rev1 § 28.4 + Doc 6 RFP-005, RFP-006, RFP-007.
- **Estado v0.1:** OCR (GD-API-0111) existía como worker, pero sin entrypoint operativo desde Ventanilla Única ni asociación a radicado.
- **Corrección:** **GD-API-0135** (individual), **GD-API-0136** (lote con separación por código de barras), **GD-API-0137** (asociación automática vía contexto activo), **GD-API-0142** (validación calidad + reemplazo con motivo). Se integra con EP-018 (`core.archivo_digital`) y dispara OCR de GD-API-0111.

### 6.b.6 GAP-13 — Salud, fallos y mantenimiento de periféricos
- **Origen:** Doc 5-rev1 § 28.7 + Doc 6 RFP-008.
- **Estado v0.1:** sin observabilidad de hardware.
- **Corrección:** **GD-API-0138** (registro de eventos + dashboard de fallos + auto-protección al detectar > 5 fallos/hora).

### 6.b.7 GAP-14 — Autenticación segura del agente local (cliente del backend)
- **Origen:** Doc 6 § 4.1 (Agente local) + Doc 6 § 8 RNFP-001.
- **Estado v0.1:** sin contrato con clientes locales; el backend asumía consumo exclusivamente desde navegador autenticado.
- **Corrección:** **GD-API-0139** — emparejamiento con token one-shot, JWT de larga duración + HMAC del body firmado con clave pública del agente; revocación inmediata por admin.

### 6.b.8 GAP-15 — Permisos específicos de periféricos
- **Origen:** Doc 5-rev1 § 28.8 + Doc 6 § 9 (12 permisos `PERM-PER-001..012`).
- **Estado v0.1:** matriz de permisos no incluía ningún permiso de periféricos.
- **Corrección:** **GD-API-0140** (seed de los 12 permisos + matriz inicial: Admin Sistema todo, Coordinador VU operación + monitoreo, Radicador operación básica, Auditor consulta).

### 6.b.9 GAP-16 — Historial unificado para auditoría
- **Origen:** Doc 6 § 8 RNFP-002.
- **Estado v0.1:** `core.evento_auditoria` solo cubría operaciones de dominio funcional.
- **Corrección:** **GD-API-0141** — vista unificada cruzando impresiones + digitalizaciones + eventos técnicos + mantenimientos por periférico, exportable para Auditor.

### 6.b.10 GAP-17 (UI) — Pantallas de operación y administración de periféricos
- **Origen:** todos los GAPs anteriores requieren UI.
- **Estado v0.1:** ninguna pantalla.
- **Corrección:** nueva **épica EP-013 UI** con **8 tickets** (GD-UI-0087..0094):
  - GD-UI-0087: Admin periféricos.
  - GD-UI-0088: Puntos de atención.
  - GD-UI-0089: Botones impresión en ficha radicado.
  - GD-UI-0090: Componente escaneo en wizard radicado.
  - GD-UI-0091: Lote digitalización.
  - GD-UI-0092: Modal reimpresión con motivo.
  - GD-UI-0093: Bandeja huérfanos (escaneos pendientes de asociación).
  - GD-UI-0094: Dashboard salud + fallos.

### 6.b.11 GAP-18 — Activación opcional por tipo de organización
- **Origen:** Doc 1 § 6 + Doc 5-rev1 § 28 introducción (operación presencial es opcional).
- **Estado v0.1:** GD-API-0011.b lista 13 módulos activables, ninguno cubre periféricos.
- **Corrección:** GD-API-0011.b extendido con módulo `ventanilla_presencial_con_perifericos` — empresa privada que opera solo online lo desactiva y no ve menús de EP-013.

### 6.b.12 GAP-19 — Documentación de integración UI ↔ Backend
- **Origen:** revisión 2026-05-23 detectó que los contratos request/response estaban dispersos entre BACKLOG.md (perspectiva backend) y UI_BACKLOG.md (perspectiva UX). No había documento canónico de payloads.
- **Estado v0.1:** sin documento de integración.
- **Corrección:** nueva carpeta [`integracion/`](integracion/) con:
  - [`README.md`](integracion/README.md) — índice maestro + convenciones (errores comunes, paginación, snapshots, archivos transversales).
  - [`INTEGRACION_E1_IDENTIDAD.md`](integracion/INTEGRACION_E1_IDENTIDAD.md) — contratos EP-001 + EP-002 + EP-019 (~50 endpoints).
  - [`INTEGRACION_E2_VENTANILLA.md`](integracion/INTEGRACION_E2_VENTANILLA.md) — contratos EP-004 + EP-005 + EP-021 (~45 endpoints, incluye periféricos completos + tabla de mapeo ticket UI ↔ endpoints).
  - Entregas 3 a 8 + RPA: pendientes (siguiente iteración).

**Cobertura tras revisión 2026-05-23:**
- Doc 5-rev1 § 28: **100%** (5 entidades + 10 reglas operativas + 10 permisos + impacto en entidades existentes — todo cubierto en EP-021 + EP-013 UI).
- Doc 6 completo: **100%** (RFP-001..008 → 12 tareas API; RNFP-001..006 → 4 RNF nuevos al Anexo B; permisos PERM-PER-011..012 → GD-API-0140).

---

## 7. Resumen ejecutivo de cobertura

| Documento | Sección/ítem auditado | Cobertura |
|---|---|---|
| Doc 1 Visión | 17 objetivos + 8 principios + 14 usuarios + 15 módulos + 7 flujos + 20 reglas + 4 estados + 7 plantillas + 13 indicadores | **100%** |
| Doc 2 RNF | 60 RNF + 10 principios + 20 requisitos críticos v1 | **100%** |
| Doc 3 Roles | 5 estados + 7 vinculaciones + 6 alcances + 19 roles + ~140 permisos + 7 menús + 6 reglas + 22 acciones críticas + 24 historias | **100%** |
| Doc 4 Mapa | 20 módulos + 30 eventos + 5 capas + 4 flujos end-to-end + 6 límites | **100%** |
| Doc 5 Modelo | 36 entidades + 10 principios + reglas históricas + 15 recomendaciones | **100%** |
| Doc 5-rev1 Periféricos (§28) | 5 entidades nuevas + 10 reglas operativas + 10 permisos + impacto en entidades existentes | **100%** |
| Doc 6 Componente Periféricos | 8 RFP + 6 RNFP + 12 permisos + 6 entidades sugeridas + arquitectura agente local + 4 alternativas técnicas + flujos operativos | **100%** |

**Resultado final:** cobertura **100%** tras añadir 7 tareas correctivas (GD-API-0122..0127) + nueva épica EP-021 (GD-API-0128..0142, 15 tareas) + nueva épica UI EP-013 (GD-UI-0087..0094, 8 tareas) + carpeta `integracion/` con contratos de payload por endpoint.

**Trabajo restante (no es gap funcional, es deuda de documentación de integración):**
- Generar `INTEGRACION_E3_BUZON.md` (EP-006).
- Generar `INTEGRACION_E4_PQRSD.md` (EP-007).
- Generar `INTEGRACION_E5_CORRESPONDENCIA.md` (EP-008).
- Generar `INTEGRACION_E6_DOCUMENTOS.md` (EP-009 + EP-010 + EP-011 + EP-018).
- Generar `INTEGRACION_E7_CORREO_IA_REPORTES.md` (EP-012 + EP-013 + EP-014).
- Generar `INTEGRACION_E8_TRD_EXPEDIENTES.md` (EP-015 + EP-016).
- Generar `INTEGRACION_FUTURO_RPA.md` (EP-017).

---

**Última actualización:** 2026-05-23 (rev. EP-021 — periféricos + carpeta `integracion/`)
**Auditoría realizada por:** revisión cruzada PDF × backlog tarea por tarea, sección por sección.
