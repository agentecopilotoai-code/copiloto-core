# Integración UI ↔ Backend — Módulo Gestión Documental

> Documento maestro: **contratos formales** de cada endpoint que el admin-panel consume del backend. Por cada endpoint se documenta el request payload, response payload (éxito y errores), permisos requeridos, eventos emitidos y la tarea UI (`GD-UI-NNNN`) que lo consume.
>
> **Por qué existe este documento.** El `BACKLOG.md` documenta los endpoints desde la perspectiva del backend (qué hace cada endpoint y por qué). El `UI_BACKLOG.md` documenta las pantallas desde la perspectiva de UX (qué ve el usuario y qué endpoints toca). Este documento es el **contrato** entre ambos: cuando el equipo backend implementa `GD-API-0024` y el equipo frontend implementa `GD-UI-0007`, ambos miran este archivo para alinearse en el shape exacto del JSON intercambiado.

## Convenciones

### Estructura de cada endpoint
Cada endpoint se documenta con esta estructura:

```
### {VERBO} {/path/del/endpoint}
**Tarea backend:** GD-API-NNNN
**Tarea(s) UI consumidoras:** GD-UI-NNNN [, GD-UI-NNNN]
**Permiso requerido:** PERM-XXX-NNN (alcance: propio | dependencia | institucional | global)
**Evento emitido:** gd.xxx.yyy (criticidad: baja | media | alta | crítica)

#### Request
... payload schema ...

#### Response 2xx
... payload schema ...

#### Errores específicos
... 4xx codes ...
```

### Convenciones de schemas
- `id: UUID` — identificador interno (nunca expuesto en URL si es sensible).
- `timestamp: ISO 8601 UTC` — formato `"2026-05-23T14:32:11.000Z"`.
- `?` después del nombre del campo = opcional. Si no se especifica, es **requerido**.
- Enums se documentan inline: `estado ∈ {activo, inactivo}`.
- Campos con `default` se marcan: `incluir_qr?: bool (default true)`.

### Respuestas comunes (no se repiten en cada endpoint)

#### 401 Unauthorized
```json
{
  "error": "unauthenticated",
  "message": "Token no provisto o inválido",
  "request_id": "req_xxxxxxxxxxxx"
}
```

#### 403 Forbidden (autorización denegada)
```json
{
  "error": "forbidden",
  "message": "El usuario no tiene el permiso PERM-XXX-NNN con alcance requerido",
  "permiso_requerido": "PERM-PQRSD-009",
  "alcance_requerido": "dependencia",
  "request_id": "req_xxxxxxxxxxxx"
}
```
> RNF-047 — el mensaje NO revela detalles del recurso (existencia, datos, ownership). Solo informa qué permiso falta.

#### 404 Not Found
```json
{
  "error": "not_found",
  "message": "El recurso solicitado no existe o no es visible para este usuario",
  "request_id": "req_xxxxxxxxxxxx"
}
```

#### 409 Conflict (estado inválido o duplicado)
```json
{
  "error": "conflict",
  "code": "radicado_ya_anulado",
  "message": "El radicado ya se encuentra en estado 'anulado'",
  "detalles": { "estado_actual": "anulado", "anulado_en": "2026-05-20T10:15:00Z" },
  "request_id": "req_xxxxxxxxxxxx"
}
```

#### 422 Unprocessable Entity (validación)
```json
{
  "error": "validation_error",
  "errores_campos": [
    { "campo": "motivo", "regla": "min_length", "mensaje": "El motivo debe tener al menos 10 caracteres", "valor_recibido": "ok" }
  ],
  "request_id": "req_xxxxxxxxxxxx"
}
```

#### 429 Too Many Requests (rate limit por identidad técnica — RPA)
```json
{
  "error": "rate_limited",
  "message": "Cuota excedida",
  "retry_after_seconds": 30,
  "request_id": "req_xxxxxxxxxxxx"
}
```
> Header HTTP: `Retry-After: 30`

### Headers obligatorios en TODAS las requests
- `Authorization: Bearer <JWT>` — token Auth0 del producto principal (RNF-005). El módulo GD no emite tokens propios.
- `X-Tenant-Id: <UUID>` — UUID del tenant activo (RLS lo valida contra el JWT). Sin este header, todos los endpoints `/api/v1/gd/*` responden 400.
- `X-Request-Id: <opaque>` — opcional desde cliente; el backend lo genera si no viene. Aparece en logs y en `request_id` de errores.

### Headers obligatorios en TODAS las responses
- `X-Request-Id: <opaque>` — siempre.
- `X-Audit-Event-Id: <UUID>` — solo en POST/PATCH/DELETE que emiten evento auditable. Permite al cliente correlacionar con la entrada en `core.evento_auditoria`.

### Paginación estándar
Todos los endpoints `GET` que devuelven listas usan paginación cursor-based:

**Request query params:**
- `limit: int (default 50, max 200)` — número de elementos a devolver.
- `cursor: string?` — opaque cursor del response previo.
- `ordenar_por: string?` — campo por el cual ordenar (depende del endpoint).
- `direccion: "asc"|"desc" (default "desc")`.

**Response wrapper:**
```json
{
  "items": [ ... ],
  "pagina": {
    "siguiente_cursor": "opaque_string_o_null",
    "total_estimado": 1247,
    "limit_aplicado": 50
  }
}
```

### Filtros de búsqueda
- Filtros estándar como query params: `desde=YYYY-MM-DD`, `hasta=YYYY-MM-DD`, `estado=`, `dependencia_id=`.
- Filtros múltiples sobre el mismo campo se separan con coma: `estado=nueva,clasificada,asignada`.
- Búsqueda de texto: `q=` (full-text sobre campos relevantes, definidos por endpoint).

### Sobre Snapshots (RNF-006)
Endpoints que devuelven recursos con historial (radicados, PQRSD, documentos firmados) incluyen objetos `*_snapshot` que congelan datos del usuario/rol/dependencia al momento de la actuación. Estos snapshots **nunca cambian** aunque el usuario/rol/dependencia se modifiquen después.

```json
{
  "actor_snapshot": {
    "usuario_id": "uuid",
    "nombre_completo": "Juan Pérez García",
    "rol_codigo": "gd.profesional",
    "rol_nombre": "Profesional Responsable",
    "dependencia_codigo": "JUR-001",
    "dependencia_nombre": "Oficina Asesora Jurídica",
    "cargo": "Profesional Especializado",
    "capturado_en": "2026-05-20T14:32:11.000Z"
  }
}
```

## Estructura del documento

Los contratos se organizan por **entrega** (siguiendo el orden de entrega del [README.md](../README.md) sección 5):

| Documento | Cubre |
|---|---|
| [E1 — Identidad y configuración](INTEGRACION_E1_IDENTIDAD.md) | EP-001 (identidad/permisos), EP-002 (perfil de organización + estructura orgánica), EP-019 (auditoría base) |
| [E2 — Ventanilla Única + Periféricos](INTEGRACION_E2_VENTANILLA.md) | EP-004 (radicación), EP-005 (terceros), EP-021 (periféricos, agente local, digitalización, impresión) |
| E3 — Buzón y tareas | EP-006 — **pendiente** |
| E4 — PQRSD | EP-007 — **pendiente** |
| E5 — Correspondencia | EP-008 — **pendiente** |
| E6 — Documentos y plantillas | EP-009 + EP-010 + EP-011 + EP-018 — **pendiente** |
| E7 — Correo, IA, reportes | EP-012 + EP-013 + EP-014 — **pendiente** |
| E8 — TRD/TVD y expedientes | EP-015 + EP-016 — **pendiente** |
| Futuro — RPA | EP-017 — **pendiente** |

Las entregas marcadas como **pendiente** se generan a demanda. Las primeras dos (E1 y E2 + periféricos) están completas porque son la base operativa de todos los flujos siguientes y porque EP-021 (periféricos) es el cambio que motivó la creación de esta documentación.

## Patrones transversales que afectan a TODOS los endpoints

### A. Sobre IA (RNF-029)
Ningún endpoint humano permite recibir directamente "decisión IA". El flujo correcto es:
1. Cliente llama `POST /api/v1/gd/ia/{operacion}` → devuelve `solicitud_ia_id`.
2. Polling o webhook trae `resultado_ia` con sugerencia + confianza.
3. Cliente muestra la sugerencia y al confirmar llama `POST /api/v1/gd/ia/sugerencias/{id}/decidir` con `decision`.
4. La aceptación dispara el endpoint humano correspondiente (clasificar, asignar, crear) **con el `sugerencia_ia_id` en el body** para trazabilidad.

### B. Sobre archivos (EP-018)
Cualquier endpoint que reciba un archivo (anexo, documento, evidencia) recibe un **`archivo_digital_id`** (UUID), nunca el binario mismo. El cliente:
1. Sube el binario a `POST /api/v1/core/archivos` (multipart, con `proposito`).
2. Recibe `archivo_digital_id`.
3. Usa ese id en el body del endpoint de dominio (radicado, documento, anexo, digitalización, evidencia).

Esto evita acoplar todos los endpoints al storage y permite reutilizar el mismo archivo en múltiples contextos.

### C. Sobre eliminación (Mandato #3)
**Ningún endpoint expone `DELETE`** sobre recursos institucionales. Las operaciones equivalentes son:
- `POST .../inactivar` con motivo
- `POST .../anular` con flujo de aprobación
- `POST .../cerrar` o `POST .../cerrar-vigencia`
- `POST .../retirar` (solo para anexos/asociaciones, no destruye el recurso)

`DELETE` solo se usa para revocar permisos o asociaciones reversibles (ej. `DELETE /api/v1/gd/roles/{codigo}/permisos/{permiso_codigo}` revoca de la matriz, no destruye el permiso).

### D. Sobre anulación (RNF-058)
Endpoints de anulación de recursos críticos (radicado, documento firmado, PQRSD cerrada) NO ejecutan la anulación directamente. Crean una `solicitud_anulacion` que debe ser aprobada por un usuario con permiso superior, **distinto al solicitante** (separación de funciones — RNF-008).

### E. Sobre snapshots (RNF-006)
Endpoints que crean actuaciones (asignar, firmar, aprobar, radicar) llaman internamente a la función `gd.capturar_snapshot_actuacion(usuario_id)` y persisten el snapshot en el evento de auditoría. El cliente UI nunca pasa snapshots — los recibe en GET cuando consulta el historial.

### F. Sobre módulos opcionales por organización
Si un endpoint pertenece a un módulo que la organización tiene desactivado (`gd.organizacion_modulo_activacion.activado=false`), responde **404** sin distinguir "no existe el endpoint" vs "está desactivado para tu organización". Esto evita filtrar configuración de otros tenants. La UI consulta `GET /api/v1/gd/organizacion/modulos` al hacer login para saber qué pantallas ocultar.

---

**Última actualización:** 2026-05-23
