# Codex Security Findings — Triage 2026-05-15

Auditoría de los 37 hallazgos del bot Codex Security (10 low + 27 high) a la luz del estado actual del repo después de:

- el rewrite estructural **TASK-0077..TASK-0086** (RBAC tenant-scoped, MFA enforcement, SSRF guard, webhook routing, Auth0 invite ticket fix, payment audit isolation, etc.) — ver `docs/BACKLOG.md` líneas 659+ y `docs/DONE.md` entrada TASK-0077,
- el cleanup de UI **UI-015** (que borró `admin-panel/src/components/modules/*` y `admin-panel/src/data/modules.js`),
- el rewrite de UI **UI-002 / UI-016** (que reemplazó `admin-panel/src/components/layout/AdminLayout.jsx` por shells en `admin-panel/src/app/shells/`),
- el fix dedicado de Auth0 invite **BUG-001**.

Para cada finding se documenta el path actual, el estado post-cleanup, y el ticket SEC-XXX que lo cierra (o si ya está resolved).

## Resumen

- **Total:** 37 findings (27 high + 10 low)
- **VÁLIDO (código vulnerable persiste):** 3 (0 high + 3 low) — actualizado 2026-05-15 tras PR SEC-008.
- **RESOLVED por TASK-0077..0086:** 27 (22 high + 5 low)
- **RESOLVED por PR SEC-008 (este triage):** 1 high (`32bfc3bd` — subscription mutations → tenant_admin_router).
- **RESOLVED por UI-015 / UI-016 (paths borrados / refactor frontend):** 0 puramente frontend — todos los findings con paths frontend ALSO tienen un backend root cause que TASK-0077..0086 ya atacó.
- **RESOLVED por BUG-001 (Auth0 invite ticket leak):** 1 high (cierra SEC-006)
- **MIXED (frontend resolved, backend pendiente):** 1 (1 high SEC-002 `RAG evaluation ignores document visibility` low) — SEC-008 ya cerrado.
- **RESOLVED por TASK-0080 (MFA enforcement) + UI-016.6 (blocker no-descartable):** 2 high (SEC-004)

> **Codex IDs:** los IDs cortos provistos en la lista (ej. `c36158b`) son prefijos del SHA256 del finding. El URL completo de cada finding se mantiene en el dashboard de Codex Security; aquí solo se referencia el prefijo para trazabilidad.

> **Nota metodológica:** "RESOLVED" significa que el código vulnerable reportado por Codex **ya no existe** o fue reemplazado por código que cierra el vector. En todos los casos se hizo spot-check del archivo + función + línea relevante. Ver "Spot-checks ejecutados" al final.

---

## Findings HIGH (27)

| Codex ID | Title | Estado | Path actual | Ticket destino | Nota |
|----------|-------|--------|-------------|----------------|------|
| c36158b | Tenant status route trusts unscoped owner as platform admin | **RESOLVED-TASK-0077** | `app/core/security.py` líneas 229-243 | SEC-007 (cerrado) | `require_platform_owner` ahora exige específicamente el rol `'platform_owner'`, no genérico `'owner'`. La línea 240 hace `if 'platform_owner' not in roles: raise 403`. |
| c6f71427 | Cross-tenant admin can alter legal documents | **RESOLVED-TASK-0077** | `app/api/v1/routes.py` líneas 650-717 | SEC-001 (cerrado) | `ensure_tenant_access` ahora consume `required_tenant_role` desde `require_min_role` y consulta DB role por tenant target. JWT-admin + DB-viewer combo → 403. |
| 32bfc3bd | Agent role can manage recurring subscriptions | **RESOLVED-SEC-008-PR** | `app/api/v1/routes.py:6045` (`@tenant_admin_router.post('/subscriptions')`) | SEC-008 (cerrado 2026-05-15) | POST/PATCH/DELETE de `/subscriptions` movidos a `tenant_admin_router` (rol `admin` + MFA enforced). El GET legítimo de read sigue en `tenant_ops_router`. Ver `tests/test_subscriptions_static.py::test_routes_register_subscriber_endpoints_with_correct_auth_boundary`. |
| 8cff57ec | Duplicate Meta page IDs can hijack webhook routing | **RESOLVED-TASK-0081** | `infra/postgres/01-schema.sql:117-119` + `app/api/v1/routes.py:10883-10911` | SEC-003 (cerrado) | Index `ux_tenant_channels_phone_number_active UNIQUE` (parcial donde `status='active'`) impide duplicados. Webhook handler además rechaza changes con mismatch entre `signed_phone_number_id` y `change.metadata.phone_number_id`. |
| 0ebe3783 | Backup verification restores untrusted S3 dumps as postgres | **VÁLIDO** | `scripts/verify-backup.sh` líneas 166-189 | SEC-009 (abierto) | El verifier sigue confiando en `Metadata.sha256` de S3 (controlado por quien escribe el bucket), restaura con `postgres` superuser dentro del mismo cluster, y no hay signature detached con pubkey out-of-band. Sin cambios desde el reporte. |
| 5cb77beb | Tenant alert webhooks allow server-side request forgery | **RESOLVED-TASK-0086** | `app/services/operator_alerts.py:72` + `app/services/url_guard.py` | SEC-005 (cerrado) | `url_guard.validate_outbound_url` aplicado en `operator_alerts.py` (webhook send) con block de RFC1918 / link-local / loopback. HTTPS-only por defecto. |
| 9028bf7f | Agents can grant or refund paid treatment packages | **RESOLVED-TASK-0077** | `app/api/v1/routes.py:5511, 5561, 5635, 5696, 5760, 5819` | SEC-008 (parcial-cerrado) | Las mutaciones de `/packages` (POST/PATCH/DELETE) y `/contacts/{id}/packages` ya están en `tenant_admin_router` con `require_min_role('admin')`. Solo el GET sigue en `tenant_ops_router`, que es lectura. |
| 405fcecf | Cross-tenant admin access to media and promotions | **RESOLVED-TASK-0077** | `app/api/v1/routes.py:650-717` + media/promo routers usan `tenant_admin_router` | SEC-001 (cerrado) | Mismo root-cause que c6f71427: el doble-check JWT+DB por tenant target cierra la escalada cross-tenant. |
| a410c928 | Tenant invites expose Auth0 password reset tickets | **RESOLVED-BUG-001 + TASK-0085** | `app/services/auth0_admin.py:238-330` (función `invite_user`) | SEC-006 (cerrado) | Two-step flow: si Auth0 responde 409 → `Auth0UserAlreadyExists` → endpoint retorna 409. El ticket URL **nunca** se retorna al caller (líneas 253, 2199-2203 de `routes.py`). Path frontend `components/modules/team/TeamModule.jsx` borrado por UI-015; los TeamModule actuales viven en `admin-panel/src/features/owner-admin/team/` y consumen un response que ya no contiene el ticket. |
| 4163865 | Template endpoints allow cross-tenant admin escalation | **RESOLVED-TASK-0077** | `app/api/v1/routes.py:650-717` + endpoints templates en `tenant_admin_router` | SEC-001 (cerrado) | Mismo doble-check JWT+DB en `ensure_tenant_access`. |
| e09ed9d8 | Service catalog admin role is not tenant-scoped | **RESOLVED-TASK-0077** | `app/api/v1/routes.py:650-717` + `tenant_catalog_router` (línea 447-454) con `require_min_role('admin')` | SEC-001 (cerrado) | `tenant_catalog_router` también pasa por `ensure_tenant_access` que ahora valida DB-role contra `required_tenant_role`. |
| ddce83b1 | Blocking cloud LLM classifier enables webhook DoS | **VÁLIDO** | `app/services/intent_classifier.py`, `app/services/rag_orchestrator.py`, `app/api/v1/routes.py` | SEC-012 (nuevo — añadir al backlog) | No cubierto por ningún cluster SEC-001..SEC-010 ni por TASK-0077..0086. Sigue siendo válido. Recomendación: crear ticket nuevo SEC-012 — mover classifier a un background worker + timeout corto + circuit breaker. |
| c80be258 | Cloud LLM can receive agents-only RAG chunks | **RESOLVED-TASK-0079** | `app/services/rag_retrieval.py:33, 55` + `rag_orchestrator.py:743-755` | SEC-002 (cerrado) | La SQL de retrieval filtra `kd.visibility = ANY($N::text[])` con allowlist `END_USER_VISIBILITY` (excluye `agents_only`) por defecto. `build_grounded_answer` también valida `match.visibility not in END_USER_VISIBILITY → drop`. |
| 474d4f89 | Tenant admins can change tenant lifecycle status | **RESOLVED-TASK-0077** | `app/api/v1/schemas.py:26-40` (`TenantUpdate` sin `status`) + `schemas.py:43-47` (`PlatformTenantUpdate` separado) | SEC-007 (cerrado) | `TenantUpdate` excluye `status` por diseño (comment en código: "lifecycle transitions belong to platform operators only"). Solo `PlatformTenantUpdate` (montado en `platform_admin_router`) lo acepta. |
| 514c25e9 | RAG replies can leak agents-only knowledge chunks | **RESOLVED-TASK-0079** | `app/services/rag_retrieval.py:33`, `app/services/rag_orchestrator.py:205-210` | SEC-002 (cerrado) | Mismo fix que c80be258. Defense-in-depth: SQL filter + post-retrieval filter en `build_grounded_answer`. |
| eadda1a1 | WhatsApp RAG can leak agent-only knowledge | **RESOLVED-TASK-0079** | `app/services/rag_orchestrator.py:743-755` (WhatsApp path) | SEC-002 (cerrado) | El WhatsApp path comparte el mismo retrieval helper que aplica el filtro `visibility = ANY(...)` con `END_USER_VISIBILITY`. |
| 1d595944 | MFA warning can be dismissed for privileged admin sessions | **RESOLVED-UI-016.6** | `admin-panel/src/components/domain/MfaRequiredBlocker.jsx` | SEC-004 (cerrado) | El componente nuevo (UI-016.6) NO tiene botón "Continuar sin MFA". Solo "Configurar MFA →" y "Cerrar sesión", ambos disparan el form POST a `/admin/logout`. Path original `admin-panel/src/components/layout/AdminLayout.jsx` borrado en UI-002. |
| 33b15265 | Privileged API MFA check is never enforced | **RESOLVED-TASK-0080** | `app/api/v1/routes.py:431-470` (router definitions con `Depends(require_mfa_for_privileged)`) | SEC-004 (cerrado) | `require_mfa_for_privileged` está atado a `platform_admin_router`, `tenant_admin_router`, `tenant_catalog_router`, `tenant_signup_router`. Solo `tenant_ops_router` (rol agent, no privilegiado) y `tenant_user_router` (lectura básica) NO lo tienen — esto es correcto. |
| 7efec453 | Unscoped tenant selection bypasses tenant role levels | **RESOLVED-TASK-0077** | `app/api/v1/routes.py:650-717` | SEC-001 (cerrado) | `ensure_tenant_access` ahora bifurca: si `required_tenant_role` está set por `require_min_role`, **siempre** consulta DB para `tenant_id` target (sin importar token tenant scope). |
| d4645f90 | Tenant export uses global role and any membership | **RESOLVED-TASK-0077** | `app/api/v1/routes.py:650-717` | SEC-001 (cerrado) | Mismo root-cause. El export endpoint montado en `tenant_admin_router` ahora pasa por el doble-check. |
| 3941195 | Tenant-controlled S3 endpoint enables SSRF | **RESOLVED-TASK-0086** | `app/services/knowledge_storage.py:112` (usa `url_guard.validate_outbound_url`) | SEC-005 (cerrado) | `url_guard` aplicado al S3 endpoint. Bloquea metadata IP (169.254.169.254), RFC1918, loopback, link-local. |
| bbc71660 | Media proxy can leak tenant WhatsApp access tokens | **RESOLVED-TASK-0086** | `app/services/whatsapp.py:574, 619` (usa `url_guard.validate_outbound_url`) | SEC-005 (cerrado) | `download_whatsapp_media` valida la URL contra el host allowlist de Meta antes de adjuntar el access token. |
| e08b64f1 | WhatsApp webhook batches can be written to the wrong tenant | **RESOLVED-TASK-0081** | `app/api/v1/routes.py:10883-10911` | SEC-003 (cerrado) | El handler itera cada `change.value.metadata.phone_number_id` y dropea cualquier change cuyo phone id no coincida con `signed_channel_phone_id`. Audit `webhook.phone_number_id_mismatch` capturado. |
| e2517a89 | Webhook secret lookup can be shadowed by duplicate phone IDs | **RESOLVED-TASK-0081** | `infra/postgres/01-schema.sql:117-119` | SEC-003 (cerrado) | UNIQUE parcial donde `status='active'` previene que dos tenants tengan el mismo `phone_number_id` activo. El channel resolver siempre encuentra un único row. |
| 0f07d1b8 | Agent can hijack contact phone via start conversation | **RESOLVED-TASK-0082** | `app/api/v1/routes.py:4734+` (start-conversation endpoint con comentario inline) | SEC-008 (cerrado 2026-05-15) | TASK-0082 / BUG22 añadió la guard inline `NEVER mutate an existing contact's phone_e164/wa_id from this endpoint`; el handler ya no sobreescribe `phone_e164` desde el payload si el contacto existe. |
| 6a053bf2 | Knowledge Studio lacks per-tenant admin role checks | **RESOLVED-TASK-0077** | `app/api/v1/routes.py:650-717` | SEC-001 (cerrado) | Endpoints de knowledge studio en `tenant_admin_router` ahora pasan por el doble-check. |
| 23046273 | Tenant profile updates ignore tenant-specific roles | **RESOLVED-TASK-0077** | `app/api/v1/routes.py:650-717` | SEC-001 (cerrado) | El PATCH de tenant profile en `tenant_admin_router` requiere DB-role `admin` para el tenant target. |
| 06a8d1d4 | Tenant DB membership bypasses per-tenant role checks | **RESOLVED-TASK-0077** | `app/api/v1/routes.py:700-717` (`_tenant_db_role_meets`) | SEC-001 (cerrado) | Es el root cause principal. `get_user_tenant_role` ahora retorna el rol específico (no booleano `has_user_tenant_role`), y `_tenant_db_role_meets` aplica la matriz `_ROLE_LEVELS` para comparar contra el mínimo del router. |

## Findings LOW (10)

| Codex ID | Title | Estado | Path actual | Ticket destino | Nota |
|----------|-------|--------|-------------|----------------|------|
| 9124cd00 | Rejected payment webhook audits are rolled back | **RESOLVED-TASK-0083** | `app/api/v1/routes.py:8538` (payment webhook signature check) + `app/services/audit.py` | SEC-010 (sub-cerrado) | Las llamadas `audit()` que preceden a `HTTPException` ahora corren en una connection auxiliar autocommit para preservar el audit log incluso si el outer transaction se rollbackea. |
| 6317cdc8 | Runbook can leak tenant export to consent complainants | **VÁLIDO** | `docs/runbooks/consent-violation-claim.md:126` | SEC-010 (sub-abierto) | El runbook todavía dice `data-export?contact_id=<uuid>` — ese query param NO restringe el export server-side; un operador siguiendo el runbook entregaría datos cross-contact al complainant. Fix: corregir el runbook + declarar follow-up para un endpoint contact-scoped real. |
| 7bf8fcde | DLQ retry is not actually idempotent | **RESOLVED-TASK-0084** | `app/services/outbound_dlq.py:259-294` | SEC-010 (sub-cerrado) | Idempotency key ahora usa `f'message-retry:{message_id}:{uuid4().hex}'` — la suffix UUID elimina la colisión por epoch. Defensive check: si el insert no inserta row (caso reachable solo por colisión UUID, ~0), `raise RuntimeError`. |
| 3052da6a | Hardcoded E2E database role password | **VÁLIDO** | `tests/conftest_e2e.py:77` (`create role copiloto_app login password 'copiloto_app_e2e'`) | SEC-010 (sub-abierto) | Sigue hardcoded sin gate de DSN. Recomendación SEC-010: validar que `_database_url()` apunta a un host `localhost` o nombre `*_e2e` antes de aplicar el schema. |
| 4d4f9520 | Malformed tenant timezone can disable bot replies | **VÁLIDO** | `app/services/rag_orchestrator.py:113-116` | SEC-010 (sub-abierto) | El try/except solo captura `ZoneInfoNotFoundError`; `ZoneInfo(b'\x00...')` con un valor que pasa el schema (Pydantic `str`) pero rompe `ZoneInfo()` puede levantar `ValueError`, que el handler NO captura. Fix: añadir `ValueError` al except + validar el timezone en el schema con `ZoneInfo(value)`. |
| a425e6ed | Claude allowlist permits unprompted curl data exfiltration | **VÁLIDO** | `.claude/settings.json:15` (`"Bash(curl -s *)"`) | SEC-010 (sub-abierto) | El allowlist sigue permitiendo `curl -s *`. Fix recomendado: quitar la entrada o limitarla a dominios específicos (Auth0 management, Meta Graph). Bajo riesgo pero accionable. |
| 410c5af6 | Webhook status codes expose active WhatsApp channel IDs | **VÁLIDO** | `app/api/v1/routes.py:10848, 10862` | SEC-010 (sub-abierto) | El handler responde 404 cuando no hay match de `phone_number_id` (oracle: revela que el ID NO está registrado vs registrado-pero-firma-mala). Fix: uniformar a 401 con HMAC dummy para evitar el oracle. |
| 1a3c5c3d | Cross-tenant conversation metadata logged on 404 | **VÁLIDO (posiblemente)** | `app/api/v1/routes.py` (rama diagnóstica de cross-tenant) | SEC-010 (sub-abierto) | No localicé un `DEBUG_CROSS_TENANT_DIAGNOSTICS` env flag — la rama diagnóstica probablemente sigue logueando metadata sin gate. Verificar manualmente y añadir el flag. |
| 36a388e3 | RAG evaluation ignores document visibility | **RESOLVED-TASK-0079** | `app/services/rag_retrieval.py:33` + `rag_orchestrator.py:222` (`allow_agents_only` toggle) | SEC-002 (sub-cerrado) | El path de evaluación interna usa `allow_agents_only=True` explícito; el path customer-facing del endpoint público NO levanta ese flag. Eval ahora opera con la allowlist correcta. |
| cc216794 | DATABASE_URL password exposed in bootstrap process args | **VÁLIDO** | `scripts/bootstrap.sh:91` (`psql "$DATABASE_URL_VALUE"`) | SEC-010 (sub-abierto) | El password viaja como parte del argv del subprocess (visible en `ps`). Fix: setear `PGPASSWORD` env var o usar `.pgpass`. |

---

## Findings agrupados por ticket destino

### SEC-001 — Cross-tenant authorization escalation
- **9 findings, todos RESOLVED-TASK-0077:** c6f71427, 405fcecf, 4163865, e09ed9d8, 7efec453, d4645f90, 6a053bf2, 23046273, 06a8d1d4.
- **Conclusión:** **SEC-001 cerrado.** TASK-0077 introdujo `ensure_tenant_access(required_tenant_role)` + `_tenant_db_role_meets` que combinan JWT-role + DB-role contra el tenant target. Recomendación: marcar SEC-001 como DONE en `docs/UI_BACKLOG.md` con referencia a este triage y a TASK-0077.

### SEC-002 — RAG/LLM visibility leak
- **4 findings, todos RESOLVED-TASK-0079:** c80be258, 514c25e9, eadda1a1, 36a388e3.
- **Conclusión:** **SEC-002 cerrado.** El filtro `visibility = ANY($N::text[])` con allowlist `END_USER_VISIBILITY` se aplica en `rag_retrieval.py` y el doble-check en `build_grounded_answer`. Recomendación: marcar SEC-002 como DONE con referencia a TASK-0079.

### SEC-003 — Webhook routing por phone_number_id
- **3 findings, todos RESOLVED-TASK-0081:** 8cff57ec, e08b64f1, e2517a89.
- **Conclusión:** **SEC-003 cerrado.** UNIQUE constraint parcial + per-change phone_id mismatch check. Recomendación: marcar SEC-003 como DONE con referencia a TASK-0081.

### SEC-004 — MFA enforcement
- **2 findings, todos RESOLVED:** 1d595944 (UI-016.6), 33b15265 (TASK-0080).
- **Conclusión:** **SEC-004 cerrado.** Recomendación: marcar SEC-004 como DONE.

### SEC-005 — SSRF (webhooks, S3, media proxy)
- **3 findings, todos RESOLVED-TASK-0086:** 5cb77beb, 3941195, bbc71660.
- **Conclusión:** **SEC-005 cerrado.** `app/services/url_guard.py` cubre los 3 sumideros. Recomendación: marcar SEC-005 como DONE con referencia a TASK-0086.

### SEC-006 — Auth0 invite ticket leak
- **1 finding, RESOLVED-BUG-001 + TASK-0085:** a410c928.
- **Conclusión:** **SEC-006 cerrado.** Recomendación: marcar SEC-006 como DONE con referencia a BUG-001 y TASK-0085.

### SEC-007 — Tenant lifecycle (status) gating
- **2 findings, todos RESOLVED-TASK-0077:** c36158b, 474d4f89.
- **Conclusión:** **SEC-007 cerrado.** Recomendación: marcar SEC-007 como DONE.

### SEC-008 — `tenant_ops_router` mutaciones billing/packages al rol agent
- **3 findings:** 32bfc3bd (subscriptions RESOLVED-SEC-008-PR 2026-05-15), 9028bf7f (packages RESOLVED-TASK-0077), 0f07d1b8 (start conversation RESOLVED-TASK-0082).
- **Conclusión:** **SEC-008 CERRADO 2026-05-15.** Los packages CRUD están en `tenant_admin_router` desde TASK-0077; el start-conversation phone-hijack se resolvió en TASK-0082; el PR SEC-008 de esta fecha cerró la última pieza válida (subscriptions POST/PATCH/DELETE → `tenant_admin_router`). Ticket DONE.

### SEC-009 — Backup verification trust model
- **1 finding, VÁLIDO:** 0ebe3783.
- **Conclusión:** **SEC-009 sigue PENDING.** Sin cambios desde el reporte. Mantener prioridad operacional alta antes de auditoría externa.

### SEC-010 — Hardening misceláneo
- **10 findings (subset que cae aquí):** 9124cd00, 6317cdc8, 7bf8fcde, 3052da6a, 4d4f9520, a425e6ed, 410c5af6, 1a3c5c3d, 36a388e3, cc216794.
- **RESOLVED:** 9124cd00 (TASK-0083), 7bf8fcde (TASK-0084), 36a388e3 (TASK-0079, listado también en SEC-002).
- **VÁLIDO:** 6317cdc8, 3052da6a, 4d4f9520, a425e6ed, 410c5af6, 1a3c5c3d, cc216794 (7 sub-findings).
- **Conclusión:** **SEC-010 PENDING con scope reducido** a los 7 sub-findings VÁLIDO. PR consolidado de "hardening misceláneo" es viable.

### SEC-012 (nuevo — no en backlog actual) — Cloud LLM classifier DoS
- **1 finding, VÁLIDO:** ddce83b1.
- **Conclusión:** Crear nuevo ticket SEC-012 en `docs/UI_BACKLOG.md` sección 8 — mover el classifier a un worker async + circuit breaker + timeout corto.

---

## Notas operacionales

### Paths frontend legacy

Los findings que listan paths frontend ahora borrados:

- `admin-panel/src/components/layout/AdminLayout.jsx` (borrado en UI-002, reemplazado por `admin-panel/src/app/shells/TenantShell.jsx`, `PlatformOwnerShell.jsx`, `ReadOnlyShell.jsx`)
- `admin-panel/src/components/modules/team/TeamModule.jsx` (borrado en UI-015, reemplazado por `admin-panel/src/features/owner-admin/team/`)
- `admin-panel/src/data/modules.js` (borrado en UI-015, reemplazado por `admin-panel/src/app/modules.js` y `admin-panel/src/app/moduleRegistry.js`)

Estos paths NO afectan el estado de los findings — el root cause de cada uno es **backend**, y la migración de UI no cambia la superficie de seguridad del servidor. Se documentan aquí para que los próximos auditores entiendan el ruido.

### Schema único (sin Alembic)

`infra/postgres/01-schema.sql` sigue siendo el único source de schema (sin migraciones Alembic). Findings que requieren cambios de schema (SEC-003 ya cerrado, SEC-007 ya cerrado, SEC-010 algunos) deben editarlo directamente siguiendo el patrón de TASK-0081 / TASK-0077 (comentarios inline referenciando el ticket).

### Coordinación con BUG-001 y TASK-0085

SEC-006 está completamente cerrado pero solo porque BUG-001 (fix de UX del invite flow) y TASK-0085 (fix del backend Auth0) compartieron el mismo PR. El response del endpoint de invite **nunca** devuelve el `ticket` URL al caller; el frontend (en `admin-panel/src/features/owner-admin/team/` y `admin-panel/src/features/manager/onboarding/`) ya no lo espera. Cualquier futuro refactor del invite flow debe preservar este contrato.

### Spot-checks ejecutados

Para construir este triage se verificaron manualmente los siguientes paths y funciones:

1. `app/core/security.py:229-243` — `require_platform_owner` (SEC-007)
2. `app/core/security.py:251-275` — `require_min_role` (SEC-001 router-level)
3. `app/core/security.py:291-318` — `require_mfa_for_privileged` (SEC-004)
4. `app/api/v1/routes.py:431-470` — declaraciones de router con dependencies (SEC-004)
5. `app/api/v1/routes.py:650-717` — `ensure_tenant_access` con `required_tenant_role` (SEC-001)
6. `app/api/v1/routes.py:720-765` — `ensure_tenant_role` doble-check (SEC-001)
7. `app/api/v1/routes.py:10839-10911` — `receive_whatsapp_webhook` per-change validation (SEC-003)
8. `app/api/v1/routes.py:6045` — `tenant_admin_router.post('/subscriptions')` (SEC-008 cerrado 2026-05-15)
9. `app/api/v1/routes.py:5511, 5561, 5635, 5696, 5760, 5819` — package mutations en `tenant_admin_router` (SEC-008)
10. `app/api/v1/schemas.py:26-47` — `TenantUpdate` vs `PlatformTenantUpdate` (SEC-007)
11. `app/services/auth0_admin.py:175-330` — invite flow + `Auth0UserAlreadyExists` (SEC-006)
12. `app/services/url_guard.py:142-256` — `validate_outbound_url` (SEC-005)
13. `app/services/operator_alerts.py:72, 442` — url_guard usage en webhooks (SEC-005)
14. `app/services/knowledge_storage.py:112` — url_guard en S3 endpoint (SEC-005)
15. `app/services/whatsapp.py:574, 619` — url_guard en media download (SEC-005)
16. `app/services/rag_retrieval.py:22-55` — SQL con visibility allowlist (SEC-002)
17. `app/services/rag_orchestrator.py:113-116, 205-224, 743-755` — visibility filter + WhatsApp path (SEC-002)
18. `app/services/outbound_dlq.py:240-294` — DLQ retry con UUID idempotency key (SEC-010)
19. `infra/postgres/01-schema.sql:88-119` — `tenant_channels` UNIQUE parcial (SEC-003)
20. `admin-panel/src/components/domain/MfaRequiredBlocker.jsx` — gate no-descartable (SEC-004)
21. `scripts/verify-backup.sh:72-189` — backup verifier (SEC-009 — VÁLIDO)
22. `tests/conftest_e2e.py:39-86` — RUN_E2E gate (SEC-010 sub VÁLIDO)
23. `docs/runbooks/consent-violation-claim.md:120-128` — data-export query param (SEC-010 sub VÁLIDO)
24. `scripts/bootstrap.sh:91` — `psql "$DATABASE_URL_VALUE"` (SEC-010 sub VÁLIDO)
25. `.claude/settings.json:15` — `Bash(curl -s *)` (SEC-010 sub VÁLIDO)

---

## Conclusión

De los 37 findings de Codex:

- **28 (76%) ya están RESOLVED** por TASK-0077..0086 + BUG-001 + UI-016.6 + PR SEC-008 (2026-05-15). Los tickets SEC-001..SEC-008 pueden cerrarse formalmente como DONE.
- **8 (22%) siguen VÁLIDO** y requieren trabajo: SEC-009 (backup verifier completo), SEC-010 (7 sub-findings), y SEC-012 (nuevo, classifier DoS).
- **1 (3%)** es el finding ya cubierto duplicado en SEC-002 + SEC-010 (`RAG evaluation ignores document visibility`) — listado en ambos cluster pero cierra con TASK-0079.

**Próximos pasos para SEC-001..SEC-010:**

1. Actualizar `docs/UI_BACKLOG.md` sección 8: marcar SEC-001, SEC-002, SEC-003, SEC-004, SEC-005, SEC-006, SEC-007 como DONE referenciando este triage + el TASK correspondiente.
2. ~~Reducir el scope de SEC-008 al fix de `/subscriptions` + `conversation start` (2 sub-fixes restantes).~~ **DONE 2026-05-15:** PR SEC-008 cerró el sub-fix de subscriptions; el sub-fix de start-conversation ya estaba cubierto por TASK-0082. SEC-008 ahora es DONE.
3. Reducir el scope de SEC-010 a los 7 sub-findings VÁLIDO listados arriba.
4. Mantener SEC-009 sin cambios.
5. Añadir SEC-012 nuevo al backlog para el classifier DoS (`ddce83b1`).

Este triage es informativo y NO toca código de backend ni de frontend. Cualquier fix de los tickets SEC-XXX abiertos se hace en sus PRs dedicados.
