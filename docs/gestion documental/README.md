# Módulo Gestión Documental con IA — Plataforma de Ventanilla Única, PQRSD y Correspondencia

> Carpeta **externa** a `docs/BACKLOG.md` y `docs/UI_BACKLOG.md`. Estos backlogs son **independientes** del producto principal (CopilotoIA), no comparten consecutivos ni se ejecutan en el mismo flujo de PRs hasta que el usuario lo indique explícitamente.

## 1. Origen funcional

Este módulo implementa la plataforma institucional descrita en los cinco documentos fuente entregados por el cliente:

| Doc fuente | Aporte al backlog |
|---|---|
| Visión y Alcance del Producto v0.1 | Alcance funcional, módulos 1–15, fases, principios funcionales, plantillas, flujos de extremo a extremo. |
| Requisitos No Funcionales v0.1 | 60 RNF (RNF-001 a RNF-060) con criterios verificables — cada épica enlaza los RNF que cumple. |
| Matriz de Roles, Permisos y Funciones v0.1 | 19 roles (ROL-001..ROL-019) + ~140 permisos (PERM-*) + reglas especiales de seguridad. |
| Mapa de Módulos Funcionales y Arquitectura Lógica v0.1 | 20 módulos (MOD-001..MOD-020) + dependencias + eventos del sistema. |
| Modelo de Datos Conceptual v0.1 | 36 entidades críticas para v1 + reglas de persistencia histórica + estados conceptuales. |

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
11. **Cero acoplamiento con CopilotoIA principal.** Este módulo vive bajo el prefijo `gd_` (schema, tablas, rutas, módulos React). Comparte autenticación e infraestructura, no lógica de negocio del producto comercial.

## 4. Cómo se navega este backlog

- `BACKLOG.md` → tareas de **backend / API / base de datos / workers / integraciones / IA**. Agrupadas en 17 épicas alineadas a los 20 módulos (MOD-001..MOD-020) del Mapa de Arquitectura.
- `UI_BACKLOG.md` → tareas de **frontend (admin-panel)** para todos los roles. Agrupadas en 12 épicas alineadas a los menús por rol que define la Matriz de Roles.

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

Entrega 2 — Ventanilla Única
    ├─ Épicas API: EP-004 (Ventanilla + Radicación), EP-005 (Terceros)
    └─ Épicas UI:  EP-002 (Ventanilla Única)

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

**Última actualización:** 2026-05-20
**Versión:** 0.1 (borrador inicial — pendiente de validación por el cliente antes de iniciar ejecución)
