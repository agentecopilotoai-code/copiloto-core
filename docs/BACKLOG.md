# Backlog operativo de CopilotoIA

Este archivo es la pila única de tareas pendientes para avanzar el producto hacia producción. Cuando el usuario diga **"continúa con la siguiente tarea"**, el agente debe tomar la **primera tarea activa** de este documento, ejecutarla completamente, retirarla de este backlog y moverla a `docs/DONE.md` con evidencia concreta de lo realizado.

## Protocolo obligatorio para agentes

1. Leer este archivo y seleccionar la primera tarea con estado `PENDING` en orden ascendente de consecutivo.
2. Ejecutar solo esa tarea, salvo que sea imposible terminarla sin una subtarea técnica estrictamente necesaria.
3. No mover una tarea a `docs/DONE.md` si no está terminada y validada.
4. Si una tarea queda bloqueada, mantenerla en este archivo y documentar el bloqueo dentro de la misma tarea.
5. Al terminar una tarea:
   - eliminarla de este archivo;
   - agregar una entrada en `docs/DONE.md` con el mismo consecutivo;
   - resumir cambios, archivos tocados, comandos ejecutados y validaciones;
   - hacer commit de los cambios.
6. Mantener consecutivos estables: no reutilizar números ya movidos a `DONE`.
7. Agregar tareas nuevas al final, con el siguiente consecutivo disponible.
8. No recrear ni duplicar configuración local ya generada: Auth0/OIDC vive en `.env.auth0.local` creado por `scripts/configure-auth0.sh` (`AUTH0_DOMAIN`, `AUTH0_ISSUER`, `AUTH0_AUDIENCE`, `AUTH0_API_IDENTIFIER`, `AUTH0_CLAIMS_NAMESPACE`, client IDs, URLs y rutas de secretos); los secretos viven en `.secrets/*` creados por `scripts/bootstrap.sh`, `scripts/generate-local-secrets.sh` o `scripts/configure-auth0.sh`. Las tareas futuras deben consumir esos nombres/archivos y no inventar variables paralelas ni hardcodear secretos.

## Revisión 2026-05-08 post-DONE

La revisión de `docs/DONE.md` contra el código confirma que el sprint **Admin Panel MVP + Knowledge Ingestion MVP** ya cubre el flujo operativo principal: tenant setup, WhatsApp onboarding/health, carga e indexado de conocimiento, prueba RAG, Operations Desk, Audit Panel y readiness por tenant. También se cerró el faltante crítico de configuración de almacenamiento de archivos de conocimiento en `TASK-0013`.

Para **producción piloto real**, quedan tareas de hardening operacional y pruebas E2E que no deben confundirse con funcionalidad MVP: RLS con dos tenants en base real, backup/restore ensayado, MFA obligatorio verificado desde Auth0, runbook de go-live ejecutable y webhook/load/idempotencia con pruebas integradas.

## Revisión 2026-05-11 post-análisis MVP

El análisis del código contra la arquitectura (`README.md` + `ARCHITECTURE.md`) revela que el flujo operativo principal está implementado (tenant setup, WhatsApp, Knowledge Studio, Operations Desk, Audit, Readiness, CI, orquestador RAG con cascada LLM), pero quedan **cinco brechas del MVP** que bloquean go-live:

1. **Embeddings reales**: el pipeline RAG usa hashes SHA256 determinísticos en lugar de embeddings ML. El índice HNSW de pgvector existe pero es semánticamente inútil con hashes, por lo que la búsqueda por similitud coseno no captura lenguaje natural.
2. **Taxonomía de intenciones incompleta**: solo se detecta booking intent con keywords. La arquitectura define 7 grupos (FAQ, agenda, servicio técnico, belleza, mascotas, riesgo, canal); sin ellos el orquestador no diferencia preguntas de precios, solicitudes de reparación o quejas.
3. **Policy engine ausente**: solo existe política básica de escalamiento (keywords + `max_bot_turns`). Faltan: detección de temas sensibles por vertical, ventana de servicio WhatsApp, risk detector (clínico/legal/garantía).
4. **Analítica sin implementar**: `GET /analytics/overview` y `GET /analytics/conversations` están definidos en la arquitectura para el rol `manager` y no existen en `routes.py`.
5. **Drill de restore sin ejecutar**: TASK-0015 generó scripts `backup-local.sh` y `restore-local.sh` pero nunca se ejecutaron con Docker real; el criterio de aceptación propio de esa tarea sigue sin cumplirse.

## Stack de tareas pendientes

### TASK-0025 — Integrar proveedor real de embeddings para retrieval semántico con pgvector

- **Objetivo:** reemplazar el hash SHA256 determinístico por embeddings ML reales para que el índice HNSW de `app.knowledge_chunks` capture semántica lingüística y el retrieval por similitud coseno funcione en producción.
- **Alcance mínimo:**
  - Agregar soporte para al menos un proveedor real de embeddings en `app/services/rag_indexing.py`: OpenAI `text-embedding-3-small` (1536 dims), Anthropic (`voyage-3-lite`, 1024 dims) u Ollama `nomic-embed-text` (768 dims).
  - Respetar el campo `RAG_EMBEDDING_PROVIDER` ya existente en `app/core/config.py`; cuando sea `local_hash` se mantiene el comportamiento actual (desarrollo sin API key); cuando sea `openai`, `anthropic` o `ollama` se llama al proveedor real.
  - Si la dimensión del proveedor difiere de 1536, hacer la columna `embedding` parametrizable o migrar el schema idempotentemente en `scripts/bootstrap.sh` (ajustar `vector(N)` y el índice HNSW).
  - Actualizar `rag_retrieval.py` para que la búsqueda ANN use `<=>` (cosine distance) con pgvector cuando los embeddings sean reales, y conserve el ranking BM25 como fallback cuando el proveedor sea `local_hash`.
  - Agregar las variables `RAG_EMBEDDING_PROVIDER`, `RAG_EMBEDDING_MODEL` y `RAG_EMBEDDING_API_KEY` (opt-in, comentadas) al `.env.example`.
  - Tests estáticos que verifiquen: (a) que `local_hash` sigue funcionando sin API key, (b) que el dispatcher selecciona el proveedor correcto según config, (c) que la dimensión del vector es coherente con la columna del schema.
- **Criterio de aceptación:** con `RAG_EMBEDDING_PROVIDER=openai` o `RAG_EMBEDDING_PROVIDER=ollama`, un documento indexado produce un vector real (no SHA256), la búsqueda ANN con pgvector devuelve chunks semánticamente relevantes ante una pregunta en lenguaje natural, y los tests estáticos pasan en CI.
- **Dependencias:** ninguna; puede ejecutarse independientemente de las demás tareas.

---

### TASK-0026 — Implementar clasificador de intenciones genérico orientado al journey de agendamiento

- **Objetivo:** la plataforma es un reemplazo de call center genérico: no conoce el tipo de negocio ni sus servicios específicos — esos datos viven en la base de conocimiento que cada tenant sube. El clasificador debe guiar a cualquier usuario desde el saludo hasta la cita confirmada, pasando por sus preguntas, sin depender de verticales hardcodeados. El clasificador actual solo detecta booking intent con keywords y no diferencia si el usuario está preguntando algo (FAQ), quiere agendar, quiere modificar una cita existente o está frustrado.
- **Alcance mínimo:**
  - Crear o ampliar `app/services/intent_classifier.py` con las siguientes intenciones genéricas (válidas para cualquier negocio que use la plataforma):
    - `greeting`: saludo inicial o reapertura de conversación; dispara mensaje de bienvenida y oferta de ayuda.
    - `faq`: pregunta sobre precios, horarios, ubicación, servicios disponibles, políticas o cualquier duda informativa; dispara búsqueda RAG en la base de conocimiento del tenant.
    - `book_appointment`: quiere agendar una cita nueva; activa el `conversation_flow` de agendamiento paso a paso.
    - `confirm_appointment`: pregunta o confirma una cita existente.
    - `reschedule_appointment`: quiere mover una cita a otro horario.
    - `cancel_appointment`: quiere cancelar.
    - `check_availability`: pregunta por disponibilidad sin comprometerse todavía; dispara consulta de slots libres.
    - `complaint_or_risk`: queja, reclamación, frustración explícita, o cualquier tema que requiera criterio humano (garantías, disputas, temas fuera del scope del negocio); fuerza handoff.
    - `out_of_scope`: mensaje sin relación con el negocio; el bot responde que solo puede ayudar con los servicios del negocio y ofrece pasar a un asesor.
    - `opt_out`: el usuario pide no recibir más mensajes; registra `opt_out` en el contacto.
  - Capa 1 (`rule-router`): keywords en español + regex para los casos más claros (saludos, "quiero agendar", "cancelar mi cita", "stop"). Devuelve intención + confianza.
  - Capa 2 (`intent-llm`): cuando confianza < 0.78, llamar al LLM disponible (cascada cloud/local existente) con un prompt corto que solo puede devolver una de las intenciones del catálogo. El contexto del negocio NO se incluye en este prompt (eso es tarea del RAG, no del clasificador).
  - Capa 3 (`fallback-human`): si tras el LLM la confianza sigue < 0.70, o si el clasificador detecta frustración/queja explícita, forzar `complaint_or_risk` → handoff.
  - El orquestador `rag_orchestrator.py` consume la intención para decidir la siguiente acción:
    - `greeting` → respuesta de bienvenida con prompt base del tenant (si existe) o mensaje genérico.
    - `faq` → búsqueda RAG; si no hay contexto suficiente → ofrecer hablar con un asesor.
    - `book_appointment` / `check_availability` → `conversation_flow` de agendamiento.
    - `confirm_appointment` / `reschedule_appointment` / `cancel_appointment` → acción sobre la cita activa del contacto.
    - `complaint_or_risk` / `out_of_scope` / `opt_out` → handoff o acción de canal.
  - El campo `conversations.current_intent` se actualiza con la intención detectada en cada turno.
  - Tests estáticos con ≥ 25 casos cubriendo todas las intenciones y los umbrales de confianza, sin depender de Docker ni API keys.
- **Criterio de aceptación:** "buenos días" → `greeting`; "cuánto cuesta?" → `faq` (dispara RAG); "quiero una cita" → `book_appointment` (activa conversation flow); "quiero cancelar" → `cancel_appointment`; "esto es una estafa" → `complaint_or_risk` (fuerza handoff); los tests estáticos pasan en CI y el campo `current_intent` de la conversación se actualiza en cada turno.
- **Dependencias:** TASK-0025 recomendada antes para mejorar la calidad del RAG que responde las FAQs, pero no bloqueante para implementar el clasificador.

---

### TASK-0027 — Implementar endpoints de analítica básica (`/analytics/overview` y `/analytics/conversations`)

- **Objetivo:** exponer los KPIs operacionales mínimos definidos en la arquitectura para el rol `manager`, necesarios para que el equipo pueda monitorear el piloto en producción.
- **Alcance mínimo:**
  - `GET /v1/analytics/overview`: devuelve para el tenant y rango de fechas (query params `from_date`, `to_date`, default últimos 30 días):
    - total de conversaciones abiertas, cerradas y en handoff
    - total de mensajes inbound y outbound
    - tasa de handoff (handoffs / conversaciones)
    - citas creadas, confirmadas y canceladas
    - solicitudes de servicio por estado
    - documentos de conocimiento activos y chunks indexados
  - `GET /v1/analytics/conversations`: devuelve funnel conversacional:
    - distribución de conversaciones por estado (`open`, `human_active`, `resolved`, etc.)
    - distribución de intenciones detectadas (agrupadas por `current_intent`)
    - tiempo promedio hasta handoff (cuando aplica)
    - top 5 intenciones más frecuentes
  - Ambos endpoints requieren rol `manager` o superior y `X-Tenant-Id`; los datos solo corresponden al tenant activo (RLS).
  - Los cálculos deben ser consultas SQL directas sobre las tablas existentes (`conversations`, `messages`, `appointments`, `service_requests`, `handoffs`), sin agregar nuevas tablas.
  - Agregar ambas rutas al módulo de Audit/Analytics del Admin Panel con visualización tabular o numérica básica (sin necesidad de librería de gráficos; cards o tablas son suficientes).
  - Tests estáticos que verifiquen la estructura del response y los controles de autorización.
- **Criterio de aceptación:** un usuario con rol `manager` puede llamar `GET /v1/analytics/overview` y obtener un JSON con los KPIs; el Admin Panel muestra los valores en una sección de analítica; un usuario con rol `agent` recibe 403; los tests estáticos pasan en CI.
- **Dependencias:** ninguna; puede ejecutarse independientemente.

---

### TASK-0028 — Implementar policy engine básico por vertical con risk detector

- **Objetivo:** cerrar la brecha entre la política básica de escalamiento actual (solo `max_bot_turns` y keywords) y el policy engine definido en la arquitectura, que debe evaluar riesgo, temas sensibles, ventana de conversación activa y límites por vertical.
- **Alcance mínimo:**
  - Crear `app/services/policy_engine.py` con función `evaluate_policy(tenant_settings, conversation, message_text, intent) -> PolicyResult`.
  - `PolicyResult` incluye: `action` (`continue_bot` | `require_handoff` | `block`), `reason` (string legible), `risk_level` (`low` | `medium` | `high`).
  - Reglas a evaluar en orden de prioridad (todas genéricas, sin verticales hardcodeados):
    1. **Intención de riesgo**: si la intención clasificada es `complaint_or_risk` → `require_handoff` con `risk_level=high` inmediatamente, sin pasar por RAG.
    2. **Ventana de servicio WhatsApp**: si `conversation.service_window_expires_at` ya pasó, solo se pueden enviar mensajes con templates aprobados; si no hay template configurado → escalar a humano.
    3. **Límite de turnos de bot**: si el número de turnos del bot en la conversación actual alcanza `tenant_settings.max_bot_turns` → `require_handoff` (el tenant configura este umbral desde el Tenant Setup Wizard).
    4. **Sin contexto RAG suficiente tras dos intentos consecutivos**: si el orquestador ya respondió dos veces con "no tengo información suficiente", forzar handoff en lugar de repetir el mismo mensaje.
  - Integrar `evaluate_policy()` en `rag_orchestrator.py` antes de generar cualquier respuesta bot.
  - Tests estáticos con ≥ 20 casos cubriendo las 4 reglas y su priorización.
- **Criterio de aceptación:** intención `complaint_or_risk` → `require_handoff` inmediato; conversación con ventana vencida sin template → handoff; llegar a `max_bot_turns` fuerza handoff; dos respuestas consecutivas sin contexto RAG fuerzan handoff; los tests estáticos pasan en CI.
- **Dependencias:** TASK-0026 recomendada antes para que el policy engine reciba la intención clasificada; el punto 2 y 3 pueden implementarse en paralelo.

---

### TASK-0029 — Ejecutar y validar drill de restore local (criterio pendiente de TASK-0015)

- **Objetivo:** cumplir el criterio de aceptación de TASK-0015 que quedó sin ejecutar por falta de Docker en el entorno de desarrollo: correr un ciclo completo backup → reset → restore en un entorno con Docker Compose y verificar que los datos se recuperan correctamente.
- **Alcance mínimo:**
  - Ejecutar `./scripts/backup-local.sh` contra un entorno Docker Compose activo con datos demo y verificar que genera el archivo de backup con dump SQL y manifiesto de objetos.
  - Ejecutar `./scripts/bootstrap.sh --reset --yes --skip-smoke` para dejar la base en estado inicial.
  - Ejecutar `./scripts/restore-local.sh <backup-file>` y validar con consultas SQL que: tenants, documentos, chunks, audit logs y al menos una conversación de demo estén presentes tras el restore.
  - Documentar el resultado (conteos antes/después) en una entrada de `docs/runbook-go-live-evidence.md` como evidencia del drill.
  - Si se detectan errores en los scripts durante la ejecución real, corregirlos in-situ y documentar los cambios en los scripts.
  - Agregar un test estático que verifique la sintaxis bash de ambos scripts con `bash -n` y que los comandos críticos (`pg_dump`, `pg_restore`, `aws s3 sync` o equivalente `mc`) estén presentes.
- **Criterio de aceptación:** restore local ejecutado con éxito con datos demo en Docker Compose; conteos documentados antes y después del restore; los scripts `backup-local.sh` y `restore-local.sh` pasan `bash -n` sin errores; evidencia registrada en `docs/runbook-go-live-evidence.md`.
- **Dependencias:** requiere entorno con Docker y Docker Compose disponible. Si el entorno de ejecución sigue sin Docker, documentar el bloqueo y no mover a DONE.

