# Plantilla de evidencia de go-live por tenant

Copiar y completar una instancia de esta plantilla por cada tenant que avance a producción.
El script `scripts/go-live-runbook.sh` genera automáticamente la sección de resultados.

---

## Evidencia de go-live — `<tenant_slug>` (`<tenant_id>`)

| Campo           | Valor                              |
|-----------------|------------------------------------|
| Tenant ID       | `<uuid>`                           |
| Tenant slug     | `<slug>`                           |
| Responsable     | `<nombre y cargo>`                 |
| Fecha inicio    | `YYYY-MM-DDTHH:MM:SSZ`             |
| Fecha fin       | `YYYY-MM-DDTHH:MM:SSZ`             |
| Resultado       | APROBADO / BLOQUEADO               |
| Readiness       | ready / not_ready                  |
| Canal WA status | healthy / degraded / not_found     |
| account_mode    | mock / live                        |
| RAG sufficient  | true / false                       |
| RAG top_score   | `<float>`                          |
| Checks ok       | `<n>`                              |
| Checks fallidos | `<n>`                              |

### Checks individuales

| Check                          | Estado | Razón                                   |
|--------------------------------|--------|-----------------------------------------|
| Tenant activo                  | ✓ / ✗  |                                         |
| Settings operativos            | ✓ / ✗  |                                         |
| Canal WhatsApp                 | ✓ / ✗  |                                         |
| Documentos activos y retrieval | ✓ / ✗  |                                         |
| Handoff humano                 | ✓ / ✗  |                                         |
| Auditoría                      | ✓ / ✗  |                                         |

### Bloqueos

<!-- Lista de bloqueos detectados o "Ninguno." -->

### Notas del operador

<!-- Observaciones adicionales, screenshots, contexto relevante -->

### Rollback ejecutado

<!-- Si se ejecutó rollback: fecha, razón y comando utilizado.
     Ejemplo:
     - Fecha: 2026-05-09T14:32:00Z
     - Razón: Canal en modo mock por error de token Meta
     - Comando: scripts/go-live-runbook.sh --tenant <uuid> --responsible "Raul M." --rollback-to-mock "Token inválido"
-->

---

## Cómo ejecutar el runbook

```bash
# Ejecución estándar (requiere API levantada)
TENANT_ID=<uuid> \
scripts/go-live-runbook.sh \
  --tenant <uuid> \
  --responsible "Nombre Apellido" \
  --smoke-question "precios manicure servicios disponibles"

# Con tokens Auth0 reales (cuando AUTH0_DOMAIN está configurado)
RUNBOOK_ADMIN_TOKEN=<token_real> \
scripts/go-live-runbook.sh \
  --tenant <uuid> \
  --responsible "Nombre Apellido" \
  --api https://api.copilotoia.com

# Rollback operativo: volver a modo mock sin SQL
scripts/go-live-runbook.sh \
  --tenant <uuid> \
  --responsible "Nombre Apellido" \
  --rollback-to-mock "Rollback preventivo: fallo en prueba de envío"
```

## Procedimiento de rollback completo

Si el go-live debe revertirse después de activar tráfico real:

1. **Cambiar canal a mock** (sin SQL): ejecutar el comando `--rollback-to-mock` de arriba.
2. **Pausar bot / forzar handoff**: ir a Operations Desk → conversación activa → forzar handoff humano.
3. **Verificar readiness post-rollback**: ejecutar el runbook de nuevo; el check `account_mode=live` fallará (esperado).
4. **Documentar**: completar la sección "Rollback ejecutado" arriba con fecha y razón.

> **Diferencia importante:**
> - `tenant.status = active`: el tenant existe y puede operar en la plataforma.
> - `channel.account_mode = live`: los mensajes salientes se envían realmente a Meta/WhatsApp.
> Ambos deben estar activos para tráfico real, pero se controlan de forma independiente.

---

*Generado por `scripts/go-live-runbook.sh`. Última actualización de plantilla: 2026-05-08.*
