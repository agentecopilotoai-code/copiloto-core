# Integración E2 — Ventanilla Única, Terceros y Periféricos

> Cubre las épicas **EP-004** (Ventanilla y radicación), **EP-005** (Terceros, ciudadanos y entidades externas) y **EP-021** (Periféricos: impresión, digitalización, códigos de barras/QR, agente local).
>
> Pre-lectura obligatoria: [`README.md`](README.md) — define convenciones, errores comunes, headers, paginación, snapshots, archivos transversales (EP-018), reglas IA.

## Índice

- [Parte A — EP-004 Ventanilla Única y radicación](#parte-a--ep-004-ventanilla-única-y-radicación)
  - [A.1 Radicación de entrada](#a1-radicación-de-entrada)
  - [A.2 Radicación de salida](#a2-radicación-de-salida)
  - [A.3 Clasificación inicial y reclasificación](#a3-clasificación-inicial-y-reclasificación)
  - [A.4 Anulación con flujo de aprobación](#a4-anulación-con-flujo-de-aprobación)
  - [A.5 Búsqueda y consulta de radicados](#a5-búsqueda-y-consulta-de-radicados)
  - [A.6 Verificación pública de constancia (sin auth)](#a6-verificación-pública-de-constancia)
  - [A.7 Cola pendiente de clasificación](#a7-cola-pendiente-de-clasificación)
  - [A.8 Correcciones menores](#a8-correcciones-menores)
  - [A.9 Radicación de contingencia](#a9-radicación-de-contingencia)
- [Parte B — EP-005 Terceros, ciudadanos y entidades externas](#parte-b--ep-005-terceros)
- [Parte C — EP-021 Periféricos](#parte-c--ep-021-periféricos)
  - [C.1 Administración de periféricos](#c1-administración-de-periféricos)
  - [C.2 Puntos de atención](#c2-puntos-de-atención)
  - [C.3 Códigos de barras y QR de radicado](#c3-códigos-de-barras-y-qr)
  - [C.4 Impresión de etiqueta y constancia](#c4-impresión-de-etiqueta-y-constancia)
  - [C.5 Digitalización individual y por lote](#c5-digitalización)
  - [C.6 Contexto activo de digitalización](#c6-contexto-activo-de-digitalización)
  - [C.7 Webhooks del agente local](#c7-webhooks-del-agente-local)
  - [C.8 Salud y mantenimiento de periféricos](#c8-salud-y-mantenimiento)
  - [C.9 Autenticación del agente local](#c9-autenticación-del-agente-local)
  - [C.10 Historial unificado para auditor](#c10-historial-unificado)

---

# Parte A — EP-004 Ventanilla Única y radicación

## A.1 Radicación de entrada

### POST `/api/v1/gd/ventanilla/radicados/entrada`
**Tarea backend:** GD-API-0024
**Tarea(s) UI consumidoras:** GD-UI-0007 (Nuevo radicado entrada — wizard 5 pasos)
**Permiso requerido:** `PERM-VU-001` (alcance: institucional para radicador VU; dependencia para radicación externa desde dependencia)
**Evento emitido:** `RadicadoCreado` (criticidad: alta — radicado es acto oficial inmutable)

#### Request
```json
{
  "canal_id": "uuid (referencia a gd.canal)",
  "punto_atencion_id": "uuid (opcional, requerido si el canal exige punto físico — ver canal.requiere_punto_atencion)",
  "asunto": "string (obligatorio, max 500)",
  "descripcion": "string (opcional, max 5000)",

  "tercero_id": "uuid (opcional — si el remitente ya existe en gd.tercero)",
  "tercero_nuevo": {
    "tipo_tercero": "persona_natural | persona_juridica | entidad_publica | entidad_privada | anonimo",
    "tipo_documento": "CC | CE | NIT | pasaporte | otro | sin_documento",
    "numero_documento": "string (requerido salvo anonimo)",
    "nombres_razon_social": "string",
    "correo": "string?",
    "telefono": "string?",
    "direccion": "string?",
    "municipio": "string?",
    "departamento": "string?",
    "pais": "string? (default 'CO')"
  },

  "dependencia_origen_id": "uuid (opcional — requerido si tipo es radicación desde dependencia)",
  "anexos": [
    {
      "archivo_digital_id": "uuid (obtenido de POST /api/v1/core/archivos antes)",
      "descripcion": "string?",
      "es_principal": "bool? (default false)"
    }
  ],

  "clasificacion_sugerida": {
    "tipo_clasificacion": "pqrsd | correspondencia_externa | correspondencia_interna | tramite | expediente",
    "sub_tipo": "string? (depende del tipo)",
    "dependencia_destino_id": "uuid?"
  },
  "sugerencia_ia_id": "uuid (opcional — si la clasificación viene de IA aceptada)",

  "es_radicacion_externa_desde_dependencia": "bool (default false)"
}
```

**Reglas de validación clave:**
- **Excluyentes:** `tercero_id` ó `tercero_nuevo`, no ambos. Sin ninguno solo se permite si el canal acepta `anonimo`.
- Si `tercero_nuevo.tipo_tercero='anonimo'`, los demás campos del tercero son opcionales (sólo se guarda el registro `anonimo` referencial).
- Cada `archivo_digital_id` debe existir, pertenecer al tenant, tener `analisis_antivirus='limpio'` (RNF-046) y MIME en whitelist (GD-API-0058). Sino → 422 con detalle por anexo.
- Si `canal_id` apunta a un canal con `requiere_punto_atencion=true` y no se envía `punto_atencion_id`, → 422.

#### Response 201
```json
{
  "id": "uuid (id interno UUID — usar siempre este, NUNCA el numero_radicado en URLs)",
  "numero_radicado": "RAD-2026-001234",
  "tipo_radicado": "entrada",
  "fecha_radicacion": "2026-05-23T14:32:11.000Z",
  "canal": { "id": "uuid", "codigo": "presencial", "nombre": "Presencial — Ventanilla Única" },
  "punto_atencion": { "id": "uuid", "nombre": "Sede Principal" },
  "asunto": "Solicitud de copia de acto administrativo 0123",
  "descripcion": "...",
  "tercero": {
    "id": "uuid",
    "tipo_tercero": "persona_natural",
    "tipo_documento": "CC",
    "numero_documento_enmascarado": "***456789",
    "nombres_razon_social": "Juan Pérez García"
  },
  "dependencia_origen": null,
  "estado": "registrado",
  "anexos_count": 2,
  "constancia": {
    "codigo_verificacion": "R2X9F4",
    "url_publica": "https://entidad.gov.co/v/RAD-2026-001234?t=ab12cd34ef56",
    "qr_archivo_digital_id": "uuid (PNG del QR para impresión)",
    "constancia_pdf_archivo_digital_id": "uuid (PDF de la constancia ya generado)"
  },
  "actor_snapshot": {
    "usuario_id": "uuid",
    "nombre_completo": "Ana López",
    "rol_codigo": "gd.radicador",
    "dependencia_codigo": "VU-001",
    "cargo": "Auxiliar Administrativo"
  },
  "creado_en": "2026-05-23T14:32:11.000Z"
}
```

> ⚠️ **`numero_radicado_enmascarado` NO existe** — el número de radicado se devuelve completo (es público por diseño, aparece en constancias). Lo que se enmascara son datos del tercero (RNF-017).

#### Errores específicos
- **422 `anexo_no_disponible`** — uno o varios `archivo_digital_id` están en antivirus pendiente o bloqueado.
- **422 `tercero_invalido`** — datos del tercero nuevo no cumplen validaciones (ej. NIT con dígito de verificación incorrecto).
- **409 `consecutivo_agotado_vigencia`** — el formato de radicado configurado se agotó. La UI debe pedir al admin abrir nueva vigencia (poco común; solo en organizaciones con miles de radicados/año y formato sin año).
- **503 `agente_local_offline`** — sólo si el canal exige impresión inmediata de constancia y el agente local del punto no responde. La UI puede ofrecer "Radicar sin impresión y reimprimir después".

---

## A.2 Radicación de salida

### POST `/api/v1/gd/ventanilla/radicados/salida`
**Tarea backend:** GD-API-0025
**Tarea(s) UI consumidoras:** GD-UI-0008
**Permiso requerido:** `PERM-VU-002` (alcance: dependencia)
**Evento emitido:** `RadicadoCreado` con `tipo_radicado='salida'`

#### Request
```json
{
  "radicado_entrada_relacionado_id": "uuid (opcional — si es respuesta a una entrada)",
  "asunto": "string",
  "descripcion": "string?",
  "dependencia_origen_id": "uuid (obligatorio — dependencia que envía)",
  "tercero_destinatario_id": "uuid (opcional)",
  "tercero_destinatario_nuevo": { ...mismo shape que tercero_nuevo de entrada... },
  "documento_principal_id": "uuid (obligatorio — debe ser un gd.documento en estado 'firmado')",
  "anexos": [ { "archivo_digital_id": "uuid" } ],
  "canal_envio_id": "uuid"
}
```

#### Response 201
Mismo shape que entrada pero con `tipo_radicado='salida'` y `radicado_entrada_relacionado_id` poblado si aplica.

#### Errores específicos
- **422 `documento_no_firmado`** — el `documento_principal_id` no está en estado `firmado` (radicar salida exige documento firmado).
- **409 `radicado_entrada_anulado`** — el radicado de entrada relacionado está anulado.

---

## A.3 Clasificación inicial y reclasificación

### POST `/api/v1/gd/ventanilla/radicados/{id}/clasificar`
**Tarea backend:** GD-API-0026
**Tarea(s) UI consumidoras:** GD-UI-0007 (paso 4 del wizard), GD-UI-0009 (drawer desde cola)
**Permiso requerido:** `PERM-VU-005` (alcance: institucional para coordinador; dependencia para profesional reclasificando dentro de su dep)
**Evento emitido:** `RadicadoClasificado` (criticidad: alta — dispara handlers como creación de PQRSD)

#### Request
```json
{
  "tipo_clasificacion": "pqrsd | correspondencia_externa | correspondencia_interna | tramite | expediente",
  "sub_tipo": "string? (ej. para PQRSD: 'peticion' | 'queja' | 'reclamo' | 'sugerencia' | 'denuncia' | 'solicitud_informacion' | 'consulta')",
  "dependencia_destino_id": "uuid? (a qué dependencia va — requerido para correspondencia y PQRSD)",
  "tipo_pqrsd_id": "uuid? (requerido si tipo_clasificacion='pqrsd' — define término legal)",
  "justificacion": "string?",
  "sugerencia_ia_id": "uuid? (traza si la clasificación viene de IA aceptada)"
}
```

#### Response 200
```json
{
  "radicado_id": "uuid",
  "clasificacion": {
    "id": "uuid",
    "tipo_clasificacion": "pqrsd",
    "sub_tipo": "peticion",
    "dependencia_destino": { "id": "uuid", "nombre": "Oficina Jurídica" },
    "tipo_pqrsd": { "id": "uuid", "nombre": "Petición general", "termino_dias": 15, "tipo_dias": "habiles" },
    "fuente": "manual | ia_aceptada | regla_automatica",
    "clasificado_por_user_id": "uuid",
    "fecha_clasificacion": "2026-05-23T14:32:11.000Z"
  },
  "recursos_creados": {
    "pqrsd_id": "uuid (si tipo='pqrsd' — el handler creó la PQRSD)",
    "correspondencia_id": null,
    "expediente_id": null
  },
  "evento_auditoria_id": "uuid"
}
```

#### Errores específicos
- **422 `tipo_pqrsd_requerido`** — clasificación es PQRSD sin `tipo_pqrsd_id`.
- **409 `radicado_ya_clasificado`** — usar `/reclasificar` en su lugar.

---

### POST `/api/v1/gd/ventanilla/radicados/{id}/reclasificar`
**Tarea backend:** GD-API-0027
**Tarea(s) UI consumidoras:** GD-UI-0012
**Permiso requerido:** `PERM-VU-006`
**Evento emitido:** `RadicadoReclasificado` (criticidad: alta)

#### Request
Mismo shape que `clasificar` + `motivo` obligatorio.
```json
{ "...todos los campos de clasificar...", "motivo": "string (min 10 chars, obligatorio)" }
```

> ⚠️ Reclasificar NO elimina la clasificación anterior — la marca `estado='reemplazada'` y deja la nueva como `vigente`. El historial es consultable con `GET /api/v1/gd/ventanilla/radicados/{id}/clasificaciones`.

---

## A.4 Anulación con flujo de aprobación

### POST `/api/v1/gd/ventanilla/radicados/{id}/solicitar-anulacion`
**Tarea backend:** GD-API-0028
**Tarea(s) UI consumidoras:** GD-UI-0011
**Permiso requerido:** `PERM-VU-015`
**Evento emitido:** `RadicadoAnulacionSolicitada` (criticidad: alta)

#### Request
```json
{
  "motivo": "string (min 20 chars, obligatorio)",
  "evidencia_archivo_digital_id": "uuid? (foto/PDF que sustenta — opcional pero recomendado)"
}
```

#### Response 201
```json
{
  "solicitud_id": "uuid",
  "tipo_entidad": "radicado",
  "entidad_afectada_id": "uuid",
  "solicitante_user_id": "uuid",
  "motivo": "...",
  "estado": "pendiente",
  "fecha_solicitud": "2026-05-23T14:32:11.000Z"
}
```

#### Errores específicos
- **409 `radicado_ya_anulado`**.
- **422 `solicitud_anulacion_duplicada`** — ya hay una solicitud `pendiente` para este radicado.

---

### POST `/api/v1/gd/ventanilla/anulaciones/{solicitud_id}/aprobar`
**Tarea backend:** GD-API-0028
**Tarea(s) UI consumidoras:** GD-UI-0011 (vista anulaciones pendientes)
**Permiso requerido:** `PERM-VU-016`
**Evento emitido:** `RadicadoAnulado` (criticidad: crítica)

#### Request
```json
{ "observacion_decision": "string?" }
```

#### Response 200
```json
{
  "solicitud_id": "uuid",
  "decision": "aprobada",
  "aprobador_user_id": "uuid",
  "fecha_decision": "2026-05-23T15:00:00.000Z",
  "radicado": {
    "id": "uuid",
    "numero_radicado": "RAD-2026-001234",
    "estado": "anulado",
    "anulado_en": "2026-05-23T15:00:00.000Z"
  }
}
```

#### Errores específicos
- **403 `solicitante_no_puede_aprobar`** — separación de funciones RNF-008. El aprobador debe ser distinto al solicitante.

---

### POST `/api/v1/gd/ventanilla/anulaciones/{solicitud_id}/rechazar`
**Tarea backend:** GD-API-0028
**Permiso requerido:** `PERM-VU-016`
**Evento emitido:** `RadicadoAnulacionRechazada` (criticidad: alta)

#### Request
```json
{ "observacion_decision": "string (obligatorio — motivo del rechazo, min 10 chars)" }
```

---

## A.5 Búsqueda y consulta de radicados

### GET `/api/v1/gd/ventanilla/radicados`
**Tarea backend:** GD-API-0029
**Tarea(s) UI consumidoras:** GD-UI-0013 (búsqueda global), GD-UI-0014 (reportes VU), GD-UI-0030 (bandejas correspondencia)
**Permiso requerido:** ninguno explícito; filtros aplican según alcance del usuario (RNF-039)

#### Request (query)
- `q?: string` — full-text sobre numero_radicado, asunto, descripción, tercero.
- `numero_radicado?: string` — búsqueda exacta.
- `tipo_radicado?: "entrada"|"salida"|"interno"` — múltiples con coma.
- `estado?: string` — múltiples con coma.
- `canal_id?: uuid`.
- `dependencia_origen_id?: uuid`, `dependencia_destino_id?: uuid`.
- `tercero_id?: uuid`.
- `fecha_radicacion_desde?: date`, `fecha_radicacion_hasta?: date`.
- `clasificado_como?: "pqrsd"|"correspondencia_externa"|...`.
- `con_anexos?: bool`.
- `alcance?: "propio"|"dependencia"|"dependencias_autorizadas"|"institucional"` — default = máximo alcance del usuario.
- `limit?, cursor?, ordenar_por?, direccion?` (estándar).

#### Response 200
```json
{
  "items": [
    {
      "id": "uuid",
      "numero_radicado": "RAD-2026-001234",
      "tipo_radicado": "entrada",
      "fecha_radicacion": "2026-05-23T14:32:11.000Z",
      "asunto": "Solicitud de copia de acto administrativo",
      "estado": "en_gestion",
      "canal": { "codigo": "presencial", "nombre": "Presencial" },
      "tercero": {
        "id": "uuid",
        "tipo_tercero": "persona_natural",
        "nombres_razon_social_enmascarado": "Juan P***",
        "tipo_documento": "CC"
      },
      "dependencia_destino": { "id": "uuid", "nombre": "Oficina Jurídica" },
      "clasificacion_vigente": { "tipo_clasificacion": "pqrsd", "sub_tipo": "peticion" },
      "anexos_count": 2,
      "tiene_pqrsd_asociada": true,
      "termino_estado": "verde",
      "dias_para_vencimiento": 12
    }
  ],
  "pagina": { "siguiente_cursor": "...", "total_estimado": 247, "limit_aplicado": 50 }
}
```

> ⚠️ Si el usuario consultante no tiene permiso `PERM-AUD-001` o equivalente, los campos sensibles del tercero vienen enmascarados (RNF-017). El UUID interno siempre se devuelve.

---

### GET `/api/v1/gd/ventanilla/radicados/{id}`
**Tarea backend:** GD-API-0029
**Tarea(s) UI consumidoras:** GD-UI-0015 (ficha completa)
**Permiso requerido:** alcance sobre el recurso (verifica visibilidad — usuario fuera de alcance recibe 404)

#### Response 200
```json
{
  "id": "uuid",
  "numero_radicado": "RAD-2026-001234",
  "tipo_radicado": "entrada",
  "fecha_radicacion": "2026-05-23T14:32:11.000Z",
  "canal": { "id": "uuid", "codigo": "presencial", "nombre": "Presencial" },
  "punto_atencion": { "id": "uuid", "nombre": "Sede Principal" },
  "asunto": "...",
  "descripcion": "...",
  "tercero": { ...shape completo si tiene permiso, enmascarado si no... },
  "dependencia_origen": null,
  "dependencia_destino": { "id": "uuid", "nombre": "Oficina Jurídica" },
  "usuario_radicador_snapshot": { ...actor_snapshot... },
  "estado": "en_gestion",
  "radicado_relacionado": { "id": "uuid", "numero_radicado": "RAD-2026-005678", "tipo": "salida" },
  "codigo_verificacion": "R2X9F4",
  "anexos": [
    {
      "id": "uuid",
      "archivo_digital_id": "uuid",
      "nombre_original": "oficio.pdf",
      "mime_type": "application/pdf",
      "tamano_bytes": 245678,
      "descripcion": "Oficio original",
      "es_principal": true,
      "cargado_en": "2026-05-23T14:32:11.000Z",
      "url_descarga": "/api/v1/gd/archivos/uuid/descargar"
    }
  ],
  "clasificaciones": {
    "vigente": { ...shape de clasificación... },
    "historial": [ { ...con estado 'reemplazada'... } ]
  },
  "recursos_asociados": {
    "pqrsd_id": "uuid",
    "correspondencia_id": null,
    "expediente_id": null
  },
  "impresiones_count": 3,
  "digitalizaciones_count": 1,
  "codigos_barras_count": 1
}
```

---

## A.6 Verificación pública de constancia

### GET `/gd/verificar/{codigo_verificacion}`
**Ruta pública** (sin `/api/v1/`, sin auth, sin tenant header)
**Tarea backend:** GD-API-0030 + GD-API-0119 (EP-020 — endpoint público dedicado)
**Tarea(s) UI consumidoras:** GD-UI-0010 (página pública de verificación)
**Permiso requerido:** ninguno (público)
**Evento emitido:** `VerificacionPublicaConstancia` (criticidad: media — para detectar enumeración)

#### Request
Sin auth. Path param: `codigo_verificacion` (alfanumérico de 6 chars).

#### Response 200
```json
{
  "valido": true,
  "numero_radicado": "RAD-2026-001234",
  "fecha_radicacion": "2026-05-23",
  "asunto_enmascarado": "Solicitud de copia de acto adm***",
  "estado_publico": "en_gestion",
  "entidad": {
    "razon_social_legal": "Alcaldía Municipal de Ejemplo",
    "logo_url_publica": "https://cdn.../logos/uuid.png"
  },
  "verificado_en": "2026-05-23T16:00:00.000Z"
}
```

> ⚠️ **NUNCA** se exponen: tercero (ni nombre completo ni documento), descripción completa, dependencia destino, anexos, clasificación, snapshot de actor. La constancia pública es prueba de que el radicado existe; los detalles son privados.

#### Response 404
Código no encontrado o expirado (no se distingue cuál — RNF-047). Cuerpo:
```json
{ "valido": false, "message": "Código de verificación no válido" }
```

> ⚠️ Rate limit estricto por IP en este endpoint (RNF-047 — evitar enumeración masiva).

---

### GET `/api/v1/gd/ventanilla/constancias/{codigo_verificacion}`
**Tarea backend:** GD-API-0030
**Tarea(s) UI consumidoras:** GD-UI-0015 (re-render de constancia desde ficha)
**Permiso requerido:** alcance sobre el radicado

Misma información que la pública pero **sin enmascaramiento** (usuario autenticado con alcance puede ver datos completos).

---

## A.7 Cola pendiente de clasificación

### GET `/api/v1/gd/ventanilla/cola/pendientes-clasificacion`
**Tarea backend:** GD-API-0031
**Tarea(s) UI consumidoras:** GD-UI-0009
**Permiso requerido:** `PERM-VU-005` (alcance: institucional para coordinador VU; dependencia para radicador su propia cola)

#### Request (query)
- `solo_mias?: bool (default false)` — si true, solo radicados creados por el usuario actual.
- `canal_id?, fecha_desde?, fecha_hasta?, q?`.
- `limit?, cursor?`.

#### Response 200
```json
{
  "items": [
    {
      "id": "uuid",
      "numero_radicado": "RAD-2026-001234",
      "fecha_radicacion": "2026-05-23T14:32:11.000Z",
      "canal": { "codigo": "presencial" },
      "asunto": "Solicitud...",
      "tercero_nombre_enmascarado": "Juan P***",
      "anexos_count": 2,
      "tiene_sugerencia_ia": true,
      "tiempo_en_cola_minutos": 47
    }
  ],
  "agregados": {
    "total_pendientes": 23,
    "promedio_tiempo_en_cola_minutos": 35,
    "mas_antiguo_minutos": 180
  },
  "pagina": { "siguiente_cursor": "...", "total_estimado": 23, "limit_aplicado": 50 }
}
```

---

## A.8 Correcciones menores

### PATCH `/api/v1/gd/ventanilla/radicados/{id}/datos-menores`
**Tarea backend:** GD-API-0032
**Tarea(s) UI consumidoras:** GD-UI-0012
**Permiso requerido:** `PERM-VU-014`
**Evento emitido:** `RadicadoCorregido` (criticidad: alta)

#### Request
```json
{
  "campo": "asunto | descripcion | tercero_nombres_razon_social | tercero_correo | tercero_telefono",
  "valor_nuevo": "string",
  "justificacion": "string (min 20 chars, obligatorio)"
}
```

> ⚠️ Lista cerrada de campos editables. **Nunca** se permite editar: `numero_radicado`, `fecha_radicacion`, `canal_id`, `tipo_radicado`. Para errores graves usar anulación.

#### Response 200
```json
{
  "radicado_id": "uuid",
  "campo_corregido": "asunto",
  "valor_anterior": "Soliitud copia acto",
  "valor_nuevo": "Solicitud copia de acto administrativo",
  "justificacion": "Typo en asunto",
  "corregido_por_user_id": "uuid",
  "evento_auditoria_id": "uuid"
}
```

---

## A.9 Radicación de contingencia

### POST `/api/v1/gd/ventanilla/radicados/contingencia`
**Tarea backend:** GD-API-0125 (EP-020)
**Tarea(s) UI consumidoras:** GD-UI-0009 (extension al detectar caída)
**Permiso requerido:** `PERM-VU-021` (solo coordinador VU + admin sistema)
**Evento emitido:** `RadicadoContingencia` (criticidad: crítica)

#### Request
```json
{
  "numero_radicado_manual": "RAD-2026-001234 (el que se asignó en papel)",
  "fecha_radicacion_real": "2026-05-23T10:30:00.000Z (timestamp del momento físico)",
  "justificacion": "string (obligatorio, min 30 chars)",
  "evidencia_contingencia_archivo_digital_id": "uuid (foto/scan de la planilla manual)",
  "...resto de campos de POST /entrada..."
}
```

#### Response 201
Mismo shape que radicado normal + flag `es_radicacion_contingencia: true` + `fecha_ingreso_sistema` (separada de `fecha_radicacion`).

---

# Parte B — EP-005 Terceros

## POST `/api/v1/gd/terceros`
**Tarea backend:** GD-API-0033
**Tarea(s) UI consumidoras:** GD-UI-0007 (inline en wizard), GD-UI-0017 (admin terceros), GD-UI-0029 (correspondencia)
**Permiso requerido:** `PERM-TER-001`
**Evento emitido:** `TerceroCreado` (criticidad: media)

### Request
```json
{
  "tipo_tercero": "persona_natural | persona_juridica | entidad_publica | entidad_privada | anonimo",
  "tipo_documento": "CC | CE | NIT | pasaporte | otro | sin_documento",
  "numero_documento": "string (requerido salvo anonimo)",
  "nombres_razon_social": "string",
  "correo": "string?",
  "telefono": "string?",
  "direccion": "string?",
  "municipio": "string?",
  "departamento": "string?",
  "pais": "string? (default 'CO')",
  "contactos_adicionales": [
    { "tipo_contacto": "correo|telefono|celular|direccion", "valor": "string", "principal": "bool" }
  ]
}
```

### Response 201
```json
{
  "id": "uuid",
  "tipo_tercero": "persona_natural",
  "tipo_documento": "CC",
  "numero_documento": "12345678",
  "nombres_razon_social": "Juan Pérez García",
  "correo": "juan@email.com",
  "telefono": "+57 300 1234567",
  "direccion": "Cra 10 # 20-30",
  "municipio": "Bogotá",
  "departamento": "Cundinamarca",
  "pais": "CO",
  "estado": "activo",
  "creado_en": "2026-05-23T14:32:11.000Z",
  "creado_por_user_id": "uuid"
}
```

### Errores específicos
- **409 `tercero_duplicado`** — ya existe un tercero con el mismo `(tipo_documento, numero_documento)` en el tenant. Response incluye:
  ```json
  {
    "error": "conflict",
    "code": "tercero_duplicado",
    "detalles": { "tercero_existente_id": "uuid" },
    "message": "Ya existe un tercero con CC 12345678"
  }
  ```
  La UI puede ofrecer "Usar el existente" llamando a GET con el id.
- **422 `nit_invalido`** — validación de dígito de verificación si `tipo_documento=NIT`.

---

## GET `/api/v1/gd/terceros/buscar`
**Tarea backend:** GD-API-0033
**Tarea(s) UI consumidoras:** GD-UI-0007 (autocomplete en wizard), GD-UI-0029
**Permiso requerido:** `PERM-TER-002`

### Request (query)
- `documento?: string` — número de documento (búsqueda exacta).
- `nombre?: string` — fuzzy search.
- `email?: string`.
- `telefono?: string`.
- `limit?: int (default 10, max 50)`.

### Response 200
```json
{
  "items": [
    {
      "id": "uuid",
      "tipo_documento": "CC",
      "numero_documento": "12345678",
      "nombres_razon_social": "Juan Pérez García",
      "correo": "juan@email.com",
      "trazabilidad_count": {
        "radicados": 5,
        "pqrsd": 2,
        "correspondencia": 1
      }
    }
  ],
  "posibles_duplicados": [
    {
      "id": "uuid",
      "nombres_razon_social": "Juan Pérez G.",
      "score_similitud": 0.87,
      "razon": "Mismo nombre, documentos diferentes"
    }
  ]
}
```

---

## PATCH `/api/v1/gd/terceros/{id}`
**Permiso requerido:** `PERM-TER-003`. **Evento:** `TerceroModificado`.

### Request
Subset de campos editables. **No editable:** `tipo_documento`, `numero_documento` (para corregir esto usar anulación + nuevo tercero).

---

## GET `/api/v1/gd/terceros/{id}/historial`
**Tarea backend:** GD-API-0034
**Tarea(s) UI consumidoras:** GD-UI-0017 (ficha tercero)
**Permiso requerido:** `PERM-TER-002` + alcance sobre los radicados del tercero

### Response 200
```json
{
  "tercero_id": "uuid",
  "totales": { "radicados": 5, "pqrsd": 2, "correspondencia": 1 },
  "items": [
    {
      "tipo": "radicado",
      "id": "uuid",
      "numero_radicado": "RAD-2026-001234",
      "fecha": "2026-05-23T14:32:11.000Z",
      "asunto": "Solicitud copia acto",
      "estado": "en_gestion"
    },
    {
      "tipo": "pqrsd",
      "id": "uuid",
      "numero_radicado": "RAD-2026-001234",
      "tipo_pqrsd": "peticion",
      "fecha_recepcion": "2026-05-23",
      "fecha_limite": "2026-06-15",
      "estado": "en_analisis"
    }
  ]
}
```

---

# Parte C — EP-021 Periféricos

> **Nota crítica:** todos los endpoints de esta parte requieren que la organización tenga activado `gd.organizacion_modulo_activacion.modulo_codigo='ventanilla_presencial_con_perifericos'`. Si está desactivado, todos responden **404** (regla F del README).

## C.1 Administración de periféricos

### POST `/api/v1/gd/perifericos`
**Tarea backend:** GD-API-0129
**Tarea(s) UI consumidoras:** GD-UI-0087 (modal de registro)
**Permiso requerido:** `PERM-PER-001` (alcance: institucional)
**Evento emitido:** `gd.periferico.registrado` (criticidad: alta)

#### Request
```json
{
  "tipo_periferico": "impresora_etiquetas | impresora_termica | impresora_convencional | escaner_plano | escaner_automatico | lector_codigo_barras | otro",
  "nombre": "string (etiqueta visible, ej. 'Zebra Counter-1')",
  "marca": "string?",
  "modelo": "string?",
  "serial": "string (obligatorio, único por tenant)",
  "dependencia_id": "uuid?",
  "punto_atencion_id": "uuid?",
  "configuracion": {
    "ancho_etiqueta_mm": 100,
    "alto_etiqueta_mm": 50,
    "dpi_default": 300,
    "encoding_comandos": "ZPL | EPL | ESC/POS | TSPL | nativo",
    "interfaz": "USB | network | bluetooth | serial",
    "otros_parametros": { }
  }
}
```

> El campo `configuracion` es libre (jsonb). El agente local interpreta los parámetros según `tipo_periferico` y `encoding_comandos`. El backend solo valida que `serial` sea único y que las FKs existan.

#### Response 201
```json
{
  "id": "uuid",
  "tipo_periferico": "impresora_etiquetas",
  "nombre": "Zebra Counter-1",
  "marca": "Zebra",
  "modelo": "GK420t",
  "serial": "ZB-12345",
  "dependencia_id": "uuid",
  "punto_atencion": { "id": "uuid", "nombre": "Sede Principal" },
  "estado": "activo",
  "configuracion": { ...lo enviado... },
  "fecha_registro": "2026-05-23T14:32:11.000Z",
  "registrado_por_user_id": "uuid",
  "agente_local_asociado": null,
  "ultima_operacion": null,
  "estadisticas_30d": { "operaciones": 0, "fallos": 0, "latencia_promedio_ms": null }
}
```

#### Errores específicos
- **409 `serial_duplicado`** — ya existe periférico con el mismo `serial` en el tenant.
- **422 `punto_atencion_inactivo`** — el `punto_atencion_id` apunta a un punto en estado `inactivo`.
- **404 `modulo_no_activado`** — la organización no tiene activado `ventanilla_presencial_con_perifericos`.

---

### GET `/api/v1/gd/perifericos`
**Permiso requerido:** `PERM-PER-010`

#### Request (query)
- `dependencia_id?, punto_atencion_id?, estado?, tipo_periferico?, q?`.
- `solo_disponibles?: bool` — si true, filtra `estado='activo'` Y agente local online.

#### Response 200
```json
{
  "items": [
    {
      "id": "uuid",
      "tipo_periferico": "impresora_etiquetas",
      "nombre": "Zebra Counter-1",
      "marca": "Zebra",
      "serial": "ZB-12345",
      "punto_atencion": { "id": "uuid", "nombre": "Sede Principal" },
      "estado": "activo",
      "agente_local_estado": "online | offline | desconocido",
      "ultima_operacion_en": "2026-05-23T14:30:00.000Z",
      "estadisticas_24h": { "operaciones": 47, "fallos": 1, "latencia_promedio_ms": 850 }
    }
  ],
  "pagina": { "siguiente_cursor": "...", "total_estimado": 12 }
}
```

---

### GET `/api/v1/gd/perifericos/{id}`
**Permiso requerido:** `PERM-PER-010`

#### Response 200
Mismo shape que POST response + lista de las últimas 10 operaciones (impresiones + digitalizaciones + eventos).

---

### PATCH `/api/v1/gd/perifericos/{id}`
**Permiso requerido:** `PERM-PER-001`. **Evento:** `gd.periferico.configuracion_modificada`.

#### Request
Cualquier subset de campos editables: `nombre`, `dependencia_id`, `punto_atencion_id`, `configuracion`.

---

### POST `/api/v1/gd/perifericos/{id}/{accion}`
Acciones: `activar | inactivar | poner-mantenimiento | retirar`.

**Permiso requerido:** `PERM-PER-002` (alcance: institucional)
**Evento emitido:** `gd.periferico.estado_cambiado` (criticidad: alta)

#### Request
```json
{
  "motivo": "string (min 10 chars, obligatorio)",
  "forzar": "bool? (default false — solo válido para inactivar/retirar; ignora operaciones en curso)"
}
```

#### Errores específicos
- **409 `periferico_en_uso`** — periférico tiene operaciones en curso (impresión o digitalización pendiente de confirmación). Response:
  ```json
  {
    "error": "conflict",
    "code": "periferico_en_uso",
    "detalles": {
      "operaciones_pendientes": 2,
      "items": [
        { "tipo": "impresion", "id": "uuid", "iniciada_en": "..." }
      ]
    }
  }
  ```
  La UI puede ofrecer reintentar con `forzar=true`.

---

## C.2 Puntos de atención

### POST `/api/v1/gd/puntos-atencion`
**Tarea backend:** GD-API-0130
**Tarea(s) UI consumidoras:** GD-UI-0088
**Permiso requerido:** `PERM-PER-001`
**Evento emitido:** `gd.punto_atencion.creado` (criticidad: media)

#### Request
```json
{
  "nombre": "string",
  "direccion": "string",
  "dependencia_responsable_id": "uuid"
}
```

#### Response 201
```json
{
  "id": "uuid",
  "nombre": "Sede Sur",
  "direccion": "Cra 50 # 80-20",
  "dependencia_responsable": { "id": "uuid", "nombre": "Ventanilla Única" },
  "estado": "activo",
  "perifericos_count": 0,
  "creado_en": "2026-05-23T14:32:11.000Z",
  "creado_por_user_id": "uuid"
}
```

---

### GET `/api/v1/gd/puntos-atencion`, `PATCH /api/v1/gd/puntos-atencion/{id}`, `POST /api/v1/gd/puntos-atencion/{id}/activar|inactivar`
Patrones equivalentes a periféricos.

### GET `/api/v1/gd/puntos-atencion/{id}/perifericos`
**Permiso requerido:** `PERM-PER-010`

#### Response 200
Lista de periféricos asignados al punto (mismo shape que GET /perifericos).

#### Errores en inactivación
- **409 `perifericos_huerfanos`** — el punto tiene periféricos asignados. Response incluye lista de periféricos para reasignar previamente.

---

## C.3 Códigos de barras y QR

### POST `/api/v1/gd/radicados/{radicado_id}/codigo-barras`
**Tarea backend:** GD-API-0131
**Tarea(s) UI consumidoras:** GD-UI-0089 (botón "Generar QR/barras")
**Permiso requerido:** `PERM-PER-003`
**Evento emitido:** `gd.codigo_barras.generado` (criticidad: media)

#### Request
```json
{
  "tipo_codigo": "codigo_barras | qr | otro"
}
```

#### Response 201
```json
{
  "id": "uuid",
  "tipo_codigo": "qr",
  "radicado_id": "uuid",
  "valor_codigo": "https://entidad.gov.co/v/RAD-2026-001234?t=ab12cd34ef56",
  "imagen": {
    "archivo_digital_id": "uuid",
    "url_temporal": "/api/v1/gd/archivos/uuid/descargar",
    "mime_type": "image/png",
    "ancho_px": 300,
    "alto_px": 300
  },
  "fecha_generacion": "2026-05-23T14:32:11.000Z",
  "generado_por_user_id": "uuid",
  "estado": "activo"
}
```

> ⚠️ **Garantía RNF-017:** el `valor_codigo` **NUNCA** contiene datos personales. Es siempre URL + token opaco. Lint en CI verifica esto.

---

### GET `/api/v1/gd/radicados/{radicado_id}/codigo-barras`
Retorna el código vigente (último generado, no anulado).

### POST `/api/v1/gd/radicados/{radicado_id}/codigo-barras/{cod_id}/anular`
**Permiso requerido:** `PERM-PER-003`. Body: `{ motivo }`.

---

## C.4 Impresión de etiqueta y constancia

### POST `/api/v1/gd/perifericos/{periferico_id}/imprimir-etiqueta`
**Tarea backend:** GD-API-0132
**Tarea(s) UI consumidoras:** GD-UI-0089
**Permiso requerido:** `PERM-PER-003`
**Evento emitido:** `gd.impresion.generada` (al recibir éxito del agente — criticidad: media)

#### Request
```json
{
  "radicado_id": "uuid",
  "formato_etiqueta": "estandar | compacta | sticker (default 'estandar')",
  "incluir_qr": "bool (default true)",
  "incluir_codigo_barras": "bool (default true)",
  "copias": "int (default 1, max 10)"
}
```

#### Response 202 (encolada para agente)
```json
{
  "impresion_id": "uuid",
  "estado": "encolada",
  "periferico": { "id": "uuid", "nombre": "Zebra Counter-1" },
  "archivo_digital_id": "uuid (PDF/PNG renderizado de la etiqueta)",
  "url_preview": "/api/v1/gd/archivos/uuid/descargar",
  "comando_para_agente": {
    "tipo": "imprimir_etiqueta",
    "encoding": "ZPL",
    "payload_base64": "eJxLzcnMS9c1MVQz1AEQUUAACAAAARsBeg==",
    "url_callback": "/api/v1/gd/perifericos/uuid/impresiones/uuid/resultado"
  },
  "expira_en": "2026-05-23T14:42:11.000Z"
}
```

> El agente local hace polling del backend (o suscripción WebSocket) y procesa los comandos `encoladas`. Tras ejecutar, reporta vía `url_callback` (ver C.7).

#### Errores específicos
- **409 `periferico_no_disponible`** — periférico inactivo o en mantenimiento.
- **409 `radicado_anulado_imprimir_marca`** — el radicado está anulado; se permite imprimir pero la etiqueta tendrá marca "ANULADO". La UI debe confirmar al usuario antes de proceder.
- **503 `agente_local_offline`** — agente no responde hace > 5 min.

---

### POST `/api/v1/gd/perifericos/{periferico_id}/reimprimir-etiqueta`
**Tarea backend:** GD-API-0133
**Tarea(s) UI consumidoras:** GD-UI-0092 (modal con motivo)
**Permiso requerido:** `PERM-PER-004` (separado del PERM-PER-003)
**Evento emitido:** `gd.impresion.reimpresion` (criticidad: alta si intentos > 1)

#### Request
```json
{
  "radicado_id": "uuid",
  "impresion_original_id": "uuid?",
  "motivo": "string (min 10 chars, obligatorio)",
  "formato_etiqueta": "estandar | compacta | sticker",
  "incluir_qr": "bool",
  "incluir_codigo_barras": "bool"
}
```

#### Response 202
Mismo shape que `imprimir-etiqueta` + campo `intentos_reimpresion: 2`.

#### Errores específicos
- **409 `requiere_aprobacion_coordinador`** — el contador `intentos_reimpresion > 3`. Response incluye `solicitud_aprobacion_id` y URL para que el coordinador apruebe.

---

### POST `/api/v1/gd/perifericos/{periferico_id}/imprimir-constancia`
**Tarea backend:** GD-API-0134
**Tarea(s) UI consumidoras:** GD-UI-0089
**Permiso requerido:** `PERM-PER-005`
**Evento emitido:** `gd.impresion.generada` con `tipo_impresion='constancia_radicacion'`

#### Request
```json
{
  "radicado_id": "uuid",
  "formato": "estandar | compacta (default 'estandar')",
  "incluir_qr": "bool (default true)",
  "copias": "int (default 1, max 5)"
}
```

#### Response 202
Mismo shape que `imprimir-etiqueta` + `tipo_impresion='constancia_radicacion'` + `archivo_digital_id` apunta al PDF A4/letter con `<InstitutionalLetterhead />`.

---

## C.5 Digitalización

### POST `/api/v1/gd/perifericos/{periferico_id}/digitalizar`
**Tarea backend:** GD-API-0135
**Tarea(s) UI consumidoras:** GD-UI-0090 (botón "Escanear" en wizard radicado)
**Permiso requerido:** `PERM-PER-006`
**Evento emitido:** `gd.digitalizacion.completada` (al recibir éxito del agente — criticidad: media)

#### Request
```json
{
  "radicado_id": "uuid (opcional si hay contexto activo registrado — ver C.6)",
  "tipo_digitalizacion": "individual",
  "calidad_dpi": "int (default 300, valores válidos: 150, 200, 300, 400, 600)",
  "color": "bool (default true)",
  "doble_cara": "bool (default false)",
  "observacion": "string?"
}
```

#### Response 202
```json
{
  "operacion_id": "uuid",
  "estado": "encolada",
  "periferico": { "id": "uuid", "nombre": "Fujitsu fi-7160" },
  "comando_para_agente": {
    "tipo": "escanear_individual",
    "config": { "dpi": 300, "color": true, "doble_cara": false },
    "url_subir_resultado": "/api/v1/core/archivos (proposito='gd.digitalizacion')",
    "url_callback": "/api/v1/gd/perifericos/uuid/digitalizaciones/uuid/resultado"
  },
  "expira_en": "2026-05-23T14:42:11.000Z"
}
```

> El agente local: (1) escanea el documento, (2) sube el PDF resultante a `/api/v1/core/archivos` con su token de agente, (3) reporta resultado al `url_callback` con el `archivo_digital_id` obtenido.

#### Cuando el callback llega, el backend automáticamente:
1. Inserta fila en `gd.digitalizacion_documento`.
2. Crea `gd.anexo` asociado al radicado (vía GD-API-0060).
3. Dispara worker OCR si aplica.
4. Emite evento auditado.

---

### POST `/api/v1/gd/perifericos/{periferico_id}/digitalizar-lote`
**Tarea backend:** GD-API-0136
**Tarea(s) UI consumidoras:** GD-UI-0091
**Permiso requerido:** `PERM-PER-007`
**Evento emitido:** `gd.digitalizacion.lote_iniciado`

#### Request
```json
{
  "radicado_id_default": "uuid? (opcional — usado si modo no detecta otro)",
  "modo_separacion": "por_pagina | por_codigo_barras | manual",
  "calidad_dpi": "int (default 300)",
  "color": "bool",
  "max_paginas": "int (default 100, max según configuración org)",
  "observacion": "string?"
}
```

#### Response 202
```json
{
  "lote_id": "uuid",
  "estado": "encolada",
  "comando_para_agente": {
    "tipo": "escanear_lote",
    "config": { "modo_separacion": "por_codigo_barras", "dpi": 300 },
    "url_callback_pagina": "/api/v1/gd/perifericos/uuid/lotes/uuid/pagina"
  }
}
```

> El agente reporta cada página/documento separado al `url_callback_pagina` conforme las va procesando.

---

### GET `/api/v1/gd/perifericos/lotes/{lote_id}`
**Permiso requerido:** `PERM-PER-007`

#### Response 200
```json
{
  "lote_id": "uuid",
  "estado": "en_progreso | completado | abandonado | error",
  "iniciado_en": "2026-05-23T14:32:11.000Z",
  "actualizado_en": "2026-05-23T14:34:00.000Z",
  "expira_en": "2026-05-23T15:02:11.000Z",
  "paginas_procesadas": 23,
  "paginas_totales_estimadas": 50,
  "modo_separacion": "por_codigo_barras",
  "documentos_separados": [
    {
      "indice": 1,
      "paginas": [1, 2, 3],
      "codigo_barras_detectado": "RAD-2026-001234",
      "radicado_asociado_id": "uuid",
      "archivo_digital_id": "uuid",
      "thumbnail_url": "/api/v1/gd/archivos/uuid/thumbnail",
      "estado_asociacion": "auto"
    },
    {
      "indice": 2,
      "paginas": [4, 5],
      "codigo_barras_detectado": null,
      "radicado_asociado_id": null,
      "archivo_digital_id": "uuid",
      "estado_asociacion": "pendiente"
    }
  ]
}
```

---

### POST `/api/v1/gd/perifericos/lotes/{lote_id}/finalizar`
**Permiso requerido:** `PERM-PER-007`
**Evento emitido:** `gd.digitalizacion.lote_finalizado`

#### Request
```json
{
  "asociaciones_manuales": [
    { "documento_indice": 2, "radicado_id": "uuid" },
    { "documento_indice": 3, "radicado_id": null, "accion": "descartar", "motivo": "..." }
  ]
}
```

#### Response 200
```json
{
  "lote_id": "uuid",
  "estado": "completado",
  "documentos_asociados": 5,
  "documentos_descartados": 0,
  "documentos_pendientes_asociacion": 0,
  "anexos_creados": ["uuid1", "uuid2", "uuid3", "uuid4", "uuid5"]
}
```

---

### POST `/api/v1/gd/digitalizaciones/{id}/reemplazar`
**Tarea backend:** GD-API-0142
**Tarea(s) UI consumidoras:** GD-UI-0090 (botón "Re-escanear esta página")
**Permiso requerido:** `PERM-PER-009`
**Evento emitido:** `gd.digitalizacion.reemplazada` (criticidad: alta)

#### Request
```json
{
  "archivo_digital_id_nuevo": "uuid",
  "motivo": "string (min 10 chars, obligatorio — ej. 'Calidad pobre, re-escaneado a 600 DPI')"
}
```

> La digitalización original **NUNCA se borra**. Queda con `estado='reemplazada'` y FK al reemplazo.

---

## C.6 Contexto activo de digitalización

### POST `/api/v1/gd/perifericos/contexto-activo`
**Tarea backend:** GD-API-0137
**Tarea(s) UI consumidoras:** GD-UI-0090 (al abrir wizard radicado), GD-UI-0091
**Permiso requerido:** `PERM-PER-006` u `007`

#### Request
```json
{
  "periferico_id": "uuid",
  "radicado_activo_id": "uuid",
  "expira_en_segundos": "int? (default 300, max 1800)"
}
```

#### Response 200
```json
{
  "contexto_id": "uuid",
  "usuario_id": "uuid",
  "periferico_id": "uuid",
  "radicado_activo_id": "uuid",
  "establecido_en": "2026-05-23T14:32:11.000Z",
  "expira_en": "2026-05-23T14:37:11.000Z"
}
```

> Una vez establecido, `POST /digitalizar` puede omitir `radicado_id` — el backend usa el contexto activo del usuario+periférico.

### DELETE `/api/v1/gd/perifericos/contexto-activo`
Libera el contexto. UI lo llama al cerrar wizard.

---

## C.7 Webhooks del agente local

> **Importante:** estos endpoints son consumidos **por el agente local**, no por la UI. Se documentan aquí para que el equipo backend conozca su contrato y el equipo del agente local sepa qué shape enviar.

### POST `/api/v1/gd/perifericos/{periferico_id}/impresiones/{impresion_id}/resultado`
**Tarea backend:** GD-API-0132/0133/0134
**Quién lo llama:** Agente local autenticado (ver C.9).
**Auth:** JWT de agente local + HMAC del body.
**Evento emitido:** `gd.impresion.generada` o `gd.impresion.fallida`

#### Request
```json
{
  "estado": "generada | fallida",
  "mensaje_error": "string? (requerido si estado='fallida')",
  "latencia_ms": "int?",
  "copias_realizadas": "int? (puede diferir del solicitado si fallaron algunas)",
  "metadata_dispositivo": {
    "voltaje_cabezal": 22.5,
    "temperatura_c": 35,
    "papel_restante_pct": 78
  }
}
```

#### Response 200
```json
{ "reconocido": true, "evento_auditoria_id": "uuid" }
```

---

### POST `/api/v1/gd/perifericos/{periferico_id}/digitalizaciones/{op_id}/resultado`
**Quién lo llama:** Agente local.
**Evento emitido:** `gd.digitalizacion.completada` / `.fallida` / `.incompleta`

#### Request
```json
{
  "estado": "correcta | fallida | incompleta",
  "archivo_digital_id": "uuid? (requerido si estado='correcta' — ya subido a /api/v1/core/archivos)",
  "numero_paginas": "int?",
  "calidad_dpi_real": "int?",
  "color_detectado": "bool?",
  "mensaje_error": "string?",
  "tiempo_total_segundos": "int?"
}
```

---

### POST `/api/v1/gd/perifericos/{periferico_id}/lotes/{lote_id}/pagina`
**Quién lo llama:** Agente local (una vez por documento separado del lote).

#### Request
```json
{
  "indice_documento": 1,
  "paginas_originales": [1, 2, 3],
  "archivo_digital_id": "uuid",
  "codigo_barras_detectado": "RAD-2026-001234?",
  "calidad_promedio": 0.92
}
```

---

## C.8 Salud y mantenimiento

### GET `/api/v1/gd/perifericos/{id}/eventos`
**Tarea backend:** GD-API-0138
**Tarea(s) UI consumidoras:** GD-UI-0094 (dashboard)
**Permiso requerido:** `PERM-PER-011`

#### Request (query)
- `desde?, hasta?, resultado?, tipo_evento?`.
- `limit?, cursor?`.

#### Response 200
```json
{
  "items": [
    {
      "id": "uuid",
      "tipo_evento": "comando_fallido",
      "fecha_hora": "2026-05-23T14:30:00.000Z",
      "usuario_snapshot": { "user_id": "uuid", "nombre": "Ana López" },
      "entidad_relacionada": { "tipo": "impresion", "id": "uuid" },
      "resultado": "fallo",
      "mensaje_error": "Atasco de papel detectado",
      "latencia_ms": 1500
    }
  ],
  "pagina": { "siguiente_cursor": "...", "total_estimado": 3 }
}
```

---

### GET `/api/v1/gd/perifericos/eventos/fallos?desde=`
**Permiso requerido:** `PERM-PER-011`

#### Response 200
```json
{
  "periodo": { "desde": "2026-05-22T00:00:00Z", "hasta": "2026-05-23T23:59:59Z" },
  "totales": { "fallos": 12, "perifericos_con_fallos": 3, "auto_protegidos": 1 },
  "por_periferico": [
    {
      "periferico_id": "uuid",
      "nombre": "Zebra Counter-2",
      "fallos_24h": 6,
      "estado_actual": "mantenimiento",
      "razon_estado": "auto_protegido por > 5 fallos en 1h",
      "ultimo_fallo": "2026-05-23T14:30:00.000Z"
    }
  ]
}
```

---

### POST `/api/v1/gd/perifericos/{id}/mantenimiento`
**Tarea backend:** GD-API-0138
**Tarea(s) UI consumidoras:** GD-UI-0094
**Permiso requerido:** `PERM-PER-012`
**Evento emitido:** `gd.mantenimiento.programado`

#### Request
```json
{
  "tipo": "preventivo | correctivo",
  "descripcion": "string",
  "fecha_estimada_fin": "2026-05-24T18:00:00.000Z?"
}
```

#### Response 201
```json
{
  "mantenimiento_id": "uuid",
  "periferico_id": "uuid",
  "tipo": "correctivo",
  "estado": "en_curso",
  "descripcion": "Limpieza cabezal + cambio rodillos",
  "iniciado_en": "2026-05-23T14:32:11.000Z",
  "iniciado_por_user_id": "uuid"
}
```

---

### POST `/api/v1/gd/perifericos/{id}/mantenimiento/{mant_id}/finalizar`
**Permiso requerido:** `PERM-PER-012`
**Evento emitido:** `gd.mantenimiento.finalizado`

#### Request
```json
{
  "observacion_final": "string",
  "costo": "decimal?",
  "repuestos": "string?",
  "reactivar_periferico": "bool (default true)"
}
```

---

## C.9 Autenticación del agente local

> Endpoints consumidos **por el admin** para emparejar agentes, y **por el agente local** para autenticarse. La UI consume solo los endpoints de admin.

### POST `/api/v1/gd/agentes-locales/emparejar`
**Tarea backend:** GD-API-0139
**Tarea(s) UI consumidoras:** GD-UI-0087 (modal "Emparejar agente local" desde admin periféricos)
**Permiso requerido:** `PERM-PER-001`
**Evento emitido:** `gd.agente_local.emparejado` (criticidad: alta)

#### Request
```json
{
  "nombre_equipo": "Counter-1-Sede-Principal",
  "perifericos": ["uuid1", "uuid2"],
  "fingerprint_publico_base64": "MIIBIjANBgkqhkiG9w0BAQEFAAOC..."
}
```

#### Response 201
```json
{
  "agente_id": "uuid",
  "token_emparejamiento": "tok_oneshot_xxxxxxxxxxxxxxxxx",
  "expira_en": "2026-05-23T14:42:11.000Z",
  "instrucciones_instalacion": {
    "url_documentacion": "https://docs.entidad.gov.co/agente-local",
    "comando_setup": "agente-gd setup --token tok_oneshot_xxx --server https://api.entidad.gov.co"
  }
}
```

> ⚠️ El `token_emparejamiento` se muestra UNA SOLA VEZ en la UI. Si el operador no lo copia, debe re-emparejar.

---

### POST `/api/v1/gd/agentes-locales/{agente_id}/revocar`
**Permiso requerido:** `PERM-PER-001`
**Evento emitido:** `gd.agente_local.revocado` (criticidad: crítica)

#### Request
```json
{ "motivo": "Equipo comprometido / robado / fin de vida útil" }
```

#### Response 200
```json
{
  "agente_id": "uuid",
  "estado": "revocado",
  "tokens_invalidados": 1,
  "perifericos_afectados": 2,
  "revocado_en": "2026-05-23T14:32:11.000Z"
}
```

> Las próximas llamadas del agente revocado responden 401. La UI debe alertar al admin sobre los periféricos que quedan sin agente activo.

---

### GET `/api/v1/gd/agentes-locales`
**Permiso requerido:** `PERM-PER-001` o `PERM-PER-010`

#### Response 200
```json
{
  "items": [
    {
      "agente_id": "uuid",
      "nombre_equipo": "Counter-1-Sede-Principal",
      "version_agente": "1.2.3",
      "estado": "activo",
      "ultimo_handshake": "2026-05-23T14:30:00.000Z",
      "estado_conexion": "online",
      "perifericos": [
        { "id": "uuid", "nombre": "Zebra Counter-1" }
      ]
    }
  ]
}
```

---

## C.10 Historial unificado

### GET `/api/v1/gd/perifericos/{id}/historial`
**Tarea backend:** GD-API-0141
**Tarea(s) UI consumidoras:** GD-UI-0094 (link "Ver historial")
**Permiso requerido:** `PERM-PER-010`

#### Request (query)
- `desde?, hasta?, tipo_operacion?` — `impresion | digitalizacion | evento_tecnico | mantenimiento | autenticacion`.
- `limit?, cursor?`.

#### Response 200
```json
{
  "periferico": { "id": "uuid", "nombre": "Zebra Counter-1" },
  "items": [
    {
      "tipo_operacion": "impresion",
      "id": "uuid",
      "fecha": "2026-05-23T14:32:11.000Z",
      "usuario_snapshot": { "user_id": "uuid", "nombre": "Ana López", "rol_codigo": "gd.radicador" },
      "entidad_relacionada": { "tipo": "radicado", "id": "uuid", "identificador": "RAD-2026-001234" },
      "resultado": "exitosa",
      "detalles": { "tipo_impresion": "etiqueta_qr", "copias": 1, "latencia_ms": 850 }
    },
    {
      "tipo_operacion": "digitalizacion",
      "id": "uuid",
      "fecha": "2026-05-23T14:30:00.000Z",
      "usuario_snapshot": { "user_id": "uuid", "nombre": "Ana López" },
      "entidad_relacionada": { "tipo": "radicado", "id": "uuid", "identificador": "RAD-2026-001234" },
      "resultado": "correcta",
      "detalles": { "numero_paginas": 3, "calidad_dpi": 300, "archivo_digital_id": "uuid" }
    }
  ]
}
```

---

### GET `/api/v1/gd/perifericos/historial-uso-global`
**Tarea backend:** GD-API-0141
**Tarea(s) UI consumidoras:** GD-UI-0094 (vista auditor)
**Permiso requerido:** `PERM-AUD-005` + `PERM-PER-011`

Vista cruzada por usuario / periférico / dependencia para Auditor.

---

### POST `/api/v1/gd/perifericos/historial/exportar?formato=csv|excel`
**Permiso requerido:** `PERM-PER-011` + `PERM-REP-008`
**Evento emitido:** `gd.perifericos.historial_consultado` (criticidad: media)

#### Request
```json
{
  "filtros": { "desde": "2026-01-01", "hasta": "2026-05-31", "periferico_id": "uuid?" },
  "formato": "csv",
  "incluir_metadata_dispositivo": false,
  "motivo": "Auditoría interna Q1 2026"
}
```

#### Response 202
```json
{
  "exportacion_id": "uuid",
  "estado": "procesando",
  "url_descarga_polling": "/api/v1/core/auditoria/exportaciones/uuid"
}
```

---

## Resumen de mapeo UI ↔ endpoints

| Ticket UI | Endpoints consumidos |
|---|---|
| **GD-UI-0007** Nuevo radicado entrada | POST `/ventanilla/radicados/entrada`, POST `/terceros`, GET `/terceros/buscar`, POST `/ia/extraer`, POST `/ventanilla/radicados/{id}/clasificar`, GET `/canales`, GET `/puntos-atencion` |
| **GD-UI-0008** Nuevo radicado salida | POST `/ventanilla/radicados/salida`, GET `/ventanilla/radicados`, GET `/documentos?estado=firmado` |
| **GD-UI-0009** Cola pendientes | GET `/ventanilla/cola/pendientes-clasificacion`, POST `/ventanilla/radicados/{id}/clasificar` |
| **GD-UI-0010** Constancia + QR | GET `/ventanilla/constancias/{codigo}`, GET `/gd/verificar/{codigo}` (pública) |
| **GD-UI-0011** Anulación | POST `/ventanilla/radicados/{id}/solicitar-anulacion`, POST `/ventanilla/anulaciones/{id}/aprobar|rechazar`, GET `/ventanilla/anulaciones?estado=pendiente` |
| **GD-UI-0012** Reclasificación + correcciones | POST `/ventanilla/radicados/{id}/reclasificar`, PATCH `/ventanilla/radicados/{id}/datos-menores` |
| **GD-UI-0013** Búsqueda global | GET `/ventanilla/radicados` |
| **GD-UI-0014** Reportes VU | GET `/ventanilla/radicados` con agregados, POST `/reportes/radicados/exportar` |
| **GD-UI-0015** Ficha radicado | GET `/ventanilla/radicados/{id}`, GET `/core/auditoria?entidad_id=`, GET `/perifericos/{id}/historial` (sección impresiones del radicado) |
| **GD-UI-0017** Admin terceros | POST/GET/PATCH `/terceros`, GET `/terceros/{id}/historial` |
| **GD-UI-0087** Admin periféricos | POST/GET/PATCH `/perifericos`, POST `/perifericos/{id}/{accion}`, GET `/agentes-locales`, POST `/agentes-locales/emparejar`, POST `/agentes-locales/{id}/revocar` |
| **GD-UI-0088** Puntos atención | POST/GET/PATCH `/puntos-atencion`, GET `/puntos-atencion/{id}/perifericos` |
| **GD-UI-0089** Impresión desde radicado | POST `/perifericos/{id}/imprimir-etiqueta`, POST `/perifericos/{id}/imprimir-constancia`, POST `/radicados/{id}/codigo-barras`, GET `/perifericos?solo_disponibles=true&tipo_periferico=impresora_etiquetas` |
| **GD-UI-0090** Escaneo en wizard | POST `/perifericos/{id}/digitalizar`, POST `/perifericos/contexto-activo`, DELETE `/perifericos/contexto-activo`, POST `/digitalizaciones/{id}/reemplazar` |
| **GD-UI-0091** Lote digitalización | POST `/perifericos/{id}/digitalizar-lote`, GET `/perifericos/lotes/{lote_id}` (polling), POST `/perifericos/lotes/{lote_id}/finalizar` |
| **GD-UI-0092** Modal reimpresión | POST `/perifericos/{id}/reimprimir-etiqueta` |
| **GD-UI-0093** Bandeja huérfanos | GET `/digitalizaciones?estado=pendiente_asociacion`, POST `/digitalizaciones/{id}/asociar`, POST `/digitalizaciones/{id}/descartar` |
| **GD-UI-0094** Dashboard salud | GET `/perifericos/eventos/fallos`, GET `/perifericos/{id}/historial`, POST `/perifericos/{id}/mantenimiento`, POST `/perifericos/{id}/mantenimiento/{mant_id}/finalizar`, POST `/agentes-locales/{id}/revocar` |

---

**Última actualización:** 2026-05-23
