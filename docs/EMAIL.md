# Email — multi-provider con fallback chain (v2.0.0)

A partir de v2.0.0, `copiloto-core` ya **no lee** `RESEND_API_KEY` del
environment. Todo el subsistema de email — provider activo, API key,
config — vive en la tabla `app.email_providers` (Postgres) y se
administra desde la admin SPA en
[`/admin/platform/email-providers`](#ui-admin).

## Modelo

```
EmailDispatcher.send(EmailMessage)
        │
        ▼
SELECT * FROM app.email_providers WHERE is_active=true ORDER BY priority ASC
        │
        ▼  per row:
   make_email_provider(row) → ResendProvider | SendGridProvider | MailgunProvider | SMTPProvider
        │
        ├── ProviderResult.success=True   → audit `sent` + return
        ├── ProviderUnavailable          → audit `retried`, try next
        ├── ProviderRateLimited          → audit `retried`, try next
        ├── ProviderInvalidConfig        → audit `failed`, return (no fallback)
        └── ProviderRejected             → audit `failed`, return (no fallback)
```

**Retryable** (fallback al siguiente):

- `ProviderUnavailable` — 5xx, network error, auth fail (401/403).
- `ProviderRateLimited` — 429 / cuota excedida.

**No retryable** (stop chain):

- `ProviderInvalidConfig` — config_jsonb roto, master key no descifra
  el ciphertext, parámetros faltantes. Arreglarlo desde la UI.
- `ProviderRejected` — 400/422 del provider (to_address inválido,
  dominio no verificado). El siguiente provider rechazaría lo mismo.

Cada attempt graba una fila en `app.email_dispatch_log` con
`status ∈ (sent, failed, retried)` para auditoría.

## Setup del primer provider (Resend ejemplo)

1. **Crear cuenta + API key**:
   - Cuenta en https://resend.com (free tier 3000 emails/mes).
   - Crear API key en https://resend.com/api-keys (empieza con `re_`).
   - Verificar dominio en https://resend.com/domains (SPF + DKIM + DMARC)
     o usar `onboarding@resend.dev` para tests.

2. **Login al admin como platform_owner** (con MFA si está activado).

3. **Navegar a `/admin/platform/email-providers`** y clic en
   **"Añadir provider"**. Form:
   - `code`: `resend-main` (identificador legible, snake-case).
   - `name`: `Resend principal` (humano).
   - `provider_type`: `Resend`.
   - `api_key`: pegar la `re_xxx` (se cifra antes de guardar).
   - `from_address_override` (opcional): si dejás vacío usa el sender
     global del `.env` (`EMAIL_FROM_ADDRESS`).
   - `priority`: `10` (menor = más prioridad).
   - `is_active`: ✓.

4. **Probar** desde la fila → modal pide `to_address`, manda email real.
   Si llega → OK, si no → el dialog muestra el error tipado.

5. (Opcional) Agregar un **segundo provider de respaldo** con
   `priority=20`. Si el primario se cae, el dispatcher cae al segundo
   automáticamente.

## Setup por provider

### Resend

`config_jsonb`: `{}` (solo necesita la api_key).

### SendGrid

`config_jsonb`: `{}` (solo api_key).

API key en https://app.sendgrid.com/settings/api_keys. Importante:
verificar single-sender o dominio antes de enviar.

### Mailgun

`config_jsonb`:
```json
{ "domain": "mg.tu-dominio.com", "region": "us" }
```

- `domain` debe ser el dominio EXACTO verificado en Mailgun.
- `region`: `us` (default, `api.mailgun.net`) o `eu`
  (`api.eu.mailgun.net`).

### SMTP (Gmail / Postfix on-prem / SES SMTP)

`config_jsonb`:
```json
{
  "host": "smtp.gmail.com",
  "port": 587,
  "username": "noreply@app.copilotoia.com",
  "use_tls": true
}
```

- `use_tls=false` solo está permitido para `host=localhost` (dev relay
  abierto). Para hosts remotos sin TLS, el constructor levanta
  `ProviderInvalidConfig`.
- La contraseña SMTP viaja como `api_key` (cifrada con la master).

## Troubleshooting

### "no_providers_configured"

La lista `app.email_providers WHERE is_active=true` está vacía. El
dispatcher devuelve `ProviderResult(success=False,
error='no_providers_configured')` y el shim legacy
(`copiloto_core.services.email`) cae a `NoopProvider` (loguea pero no
envía). **Solución**: agregar al menos un provider activo desde la UI.

### "Stored secret cannot be decrypted with the current master key"

La master Fernet (`AI_PROVIDER_MASTER_KEY`) rotó sin re-cifrar las
filas viejas. **Solución**: rotar manualmente — leer cada
`api_key_ciphertext` con la master vieja, re-cifrar con la nueva,
hacer `PATCH` con el nuevo api_key (la UI hace `PATCH
/v1/platform/email-providers/{id}` con `api_key=...nuevo plaintext...`).

### "ProviderInvalidConfig: mailgun config invalid"

El `config_jsonb` no cumple el shape esperado. Validá contra la tabla
de setup por provider arriba.

### "ProviderRejected: dominio no verificado"

El provider rechazó el envío porque el `from_address` no está en
SPF/DKIM/DMARC verificado. Verificalo en el dashboard del provider
(Resend → Domains, SendGrid → Sender Authentication, etc.).

### "ProviderUnavailable: 401" → ¿API key revocada?

Rotá la key:
1. UI → fila del provider → Editar.
2. Pegar la api_key nueva en el campo "API key" (vacío = no rotar; si
   tipeás algo reemplaza la actual).
3. Guardar.

## Audit log

Cada attempt (sent | retried | failed) graba en
`app.email_dispatch_log`:

```sql
SELECT to_address, subject, status, error_message, latency_ms, dispatched_at
FROM app.email_dispatch_log
WHERE email_provider_id = '<provider-uuid>'
ORDER BY dispatched_at DESC
LIMIT 50;
```

Útil para debug cross-provider (qué provider falló cuándo) y para
métricas de salud (tasa de éxito por provider).

## BREAKING CHANGE — upgrade desde 1.x

- **Antes**: `RESEND_API_KEY` (o `_FILE`) en `.env`.
- **Ahora**: configurar provider(s) desde la UI tras correr
  la migration `30-email-providers.sql` (la incluye automáticamente
  `python -m copiloto_core bootstrap`).
- **Compat**: `copiloto_core.services.email.get_email_provider()` sigue
  funcionando — internamente delega al nuevo `EmailDispatcher`.
- **Removido**: `Settings.resend_api_key`,
  `Settings.resend_api_key_file`, módulo
  `copiloto_core.services.email.ResendProvider` (instalado directo).

## UI admin

Página: `/admin/platform/email-providers` (capability:
`platform.ai_providers.configure`, restringida a platform_owner + MFA).

Acciones:
- Listar providers (sin exponer api_key, solo `has_api_key` bool).
- Crear / editar / borrar / **Probar** (envía email real al
  destinatario que indiques).

## Referencia rápida

| Archivo                                                             | Qué hace                                |
|---------------------------------------------------------------------|------------------------------------------|
| `copiloto_core/email/__init__.py`                                   | API pública (`EmailDispatcher`, `EmailMessage`) |
| `copiloto_core/email/providers/base.py`                             | ABC + excepciones tipadas                |
| `copiloto_core/email/providers/{resend,sendgrid,mailgun,smtp}.py`   | 4 adapters                               |
| `copiloto_core/email/providers/factory.py`                          | Row de DB → adapter concreto             |
| `copiloto_core/email/dispatcher.py`                                 | Fallback chain + audit                   |
| `copiloto_core/platform_admin/email_provider_routes.py`             | CRUD + test endpoint                     |
| `copiloto_core/platform_schema/30-email-providers.sql`              | Schema DB (`app.email_providers`)        |
| `admin-panel/src/features/platform/email-providers/`                | UI admin SPA                             |
