# CLI Reference — `python -m copiloto_core`

Catálogo completo de subcomandos del CLI con ejemplos.

> Para el flujo de onboarding completo (cero → SaaS corriendo), ver
> [QUICKSTART.md](QUICKSTART.md). Para Auth0, ver [AUTH0.md](AUTH0.md).
> Para construir tu propio módulo, ver [EXTENDING.md](EXTENDING.md).

---

## Catálogo

```
$ python -m copiloto_core --help

  version              Imprime la versión instalada
  new-project NAME     Bootstrapea un nuevo proyecto consumer del core
  bootstrap            Aplica el schema platform del core en la DB
  migrate --module=X   Aplica migrations pendientes de un módulo
  generate-secrets     Reemplaza CHANGE_ME en .env con valores random
  auth0-configure      Configura tenant Auth0 vía Management API
  backup-local         pg_dump local + cifra con GPG
  restore-local        Restaura un backup local con verificación
  backup-cloud         Backup automatizado a S3 con GPG
  verify-backup        Verifica integridad GPG de un backup cloud
  smoke-test           Curl health check de endpoints públicos
  reset-local --yes    Nuke volúmenes Docker locales (DESTRUCTIVO)
```

---

## Comandos del lifecycle del proyecto

### `version`

Imprime la versión del core instalada. Útil para confirmar upgrades
y reportar bugs.

```bash
python -m copiloto_core version
# → copiloto-core 1.4.0
```

**Exit codes**: siempre `0`.

---

### `new-project NAME [opciones]`

Scaffolder. Análogo a `django-admin startproject`. Genera un repo
Python listo para `pip install -e ".[dev]" && ./scripts/dev-up.sh`.

```bash
python -m copiloto_core new-project mi-saas
python -m copiloto_core new-project mi-saas --with-infra
python -m copiloto_core new-project mi-saas --module-name=alertas
python -m copiloto_core new-project mi-saas --git-protocol=ssh
python -m copiloto_core new-project mi-saas --target-dir=/tmp/mi-saas
```

**Flags**:

| Flag | Default | Para qué |
|---|---|---|
| `--target-dir=PATH` | `./NAME` | Dónde escribir. Debe estar vacío o no existir. |
| `--module-name=NAME` | `<package>_modulo` | Nombre snake_case del módulo demo. |
| `--git-protocol=https\|ssh` | `https` | Protocolo del pin del core en `pyproject.toml`. |
| `--with-infra` | `false` | Incluir `docker-compose.yml` + `scripts/dev-up.sh` + `.secrets/.gitkeep`. |

**Output** (con `--with-infra`):

```
satguajira/
├── pyproject.toml              # pin a copiloto-core@vX.Y.Z (https default)
├── .env.example                # 11 keys, 5 CHANGE_ME placeholders
├── .gitignore                  # excluye .env, .secrets/, venv, etc.
├── README.md                   # quickstart específico del proyecto
├── docker-compose.yml          # postgres + redis + minio
├── scripts/dev-up.sh           # 755, compose up → bootstrap → migrate → uvicorn
├── .secrets/.gitkeep
├── satguajira/main.py          # app = create_app(...)
├── satguajira/__init__.py
├── satguajira_modulo/__init__.py    # exporta module = CoreModule(...)
├── satguajira_modulo/routers.py
└── satguajira_modulo/migrations/001_init.sql
```

**Exit codes**: `0` éxito, `2` config error (nombre inválido, target dir con contenido, etc.).

---

### `generate-secrets`

Reemplaza los `CHANGE_ME` en `.env` con valores random seguros.
Idempotente: si no quedan CHANGE_ME, no hace nada.

```bash
cd mi-saas/
python -m copiloto_core generate-secrets
```

**Comportamiento**:

- Si `.env` no existe pero `.env.example` sí → copia .example → .env primero.
- Si `.env` no existe ni `.env.example` → error con exit 2.
- Si `.env` existe → edita en lugar.
- **NO toca** hostnames, project name, bucket, ni nada que no matchee `CHANGE_ME`.
- Sincroniza passwords inline:
  - `APP_DB_PASSWORD` → password en `DATABASE_URL` (user `copiloto_app`).
  - `POSTGRES_PASSWORD` → password en `DATABASE_ADMIN_URL` (user `postgres`).
- `chmod 600` al `.env` final (solo owner puede leer).

**Vars que reemplaza** (con bytes random base64-urlsafe):

| Variable | Bytes |
|---|---|
| `APP_DB_PASSWORD` | 24 |
| `POSTGRES_PASSWORD` | 24 |
| `JWT_SECRET` | 48 |
| `S3_SECRET_ACCESS_KEY` | 32 |
| `SERVICE_TOKEN` | 36 |
| `AI_PROVIDER_MASTER_KEY` | 32 (Fernet) |

**Exit codes**: `0` éxito (incluso si no hizo nada), `2` config error (sin .env ni .env.example).

---

### `bootstrap [opciones]`

Aplica el schema platform del core (`app.*`) en una DB. Idempotente.

```bash
python -m copiloto_core bootstrap                    # solo schema, sin user
python -m copiloto_core bootstrap --create-app-user  # schema + crea rol app
python -m copiloto_core bootstrap --no-seed          # sin tenant demo
```

**Lee del entorno** (o `.env` vía python-dotenv):

- `DATABASE_ADMIN_URL` — requerido. URL del user admin (postgres).
- `APP_DB_USER` + `APP_DB_PASSWORD` — requeridos si `--create-app-user`.

**Flags**:

| Flag | Para qué |
|---|---|
| `--no-seed` | No aplicar `20-seed.sql` (sin tenant demo). Para producción. |
| `--create-app-user` | Crea el rol runtime de la app (`copiloto_app`) con APP_DB_PASSWORD. |
| `--app-user=NAME` | Override de APP_DB_USER del entorno. |
| `--app-password=PASS` | Override de APP_DB_PASSWORD del entorno. |

**Orden de operaciones** (importante por chicken-and-eggs):

1. Si `--create-app-user`: crear el rol (sin grants, schema `app` no existe aún).
2. Aplicar `10-core.sql` (crea schema + tablas + GRANTs internos a copiloto_app).
3. Aplicar `20-seed.sql` (con `app.allow_seed=true` para bypassear el guard).
4. Si `--create-app-user`: aplicar GRANTs finales sobre `app.*` (idempotente).

**Exit codes**: `0` éxito, `2` config error (URL faltante), `3` SQL error.

---

### `migrate --module=CODE`

Aplica migrations pendientes del módulo indicado.

```bash
python -m copiloto_core migrate --module=mi_saas_modulo
```

**Requiere**:

- `DATABASE_ADMIN_URL` en el entorno (DDL como `CREATE SCHEMA` necesita superuser).
- El paquete Python del módulo debe ser importable: `import <code>` no debe fallar.
- El paquete debe exportar `module: CoreModule` en su `__init__.py`.

**Comportamiento**:

- Trackea aplicadas en `app.schema_migrations` con SHA-256.
- Si una migration ya aplicada fue MODIFICADA después → aborta con
  `MigrationChecksumMismatchError` (fail-closed, evita drift).
- Sin migrations pendientes → no-op idempotente.

**Exit codes**: `0` éxito, `2` config error, `3` SQL error o checksum mismatch.

---

## Comandos operacionales

Estos son thin wrappers Python sobre scripts bash bien probados que
viven en `copiloto_core/scripts/`. El consumer nunca los ve directo —
los invoca vía CLI.

### `auth0-configure [args bash pass-through]`

Configura tenant Auth0 vía Management API. Ver [AUTH0.md](AUTH0.md)
para el flujo completo.

```bash
export MGMT_CLIENT_ID=xxx MGMT_CLIENT_SECRET=yyy AUTH0_DOMAIN=zzz
python -m copiloto_core auth0-configure
unset MGMT_CLIENT_ID MGMT_CLIENT_SECRET
```

Escribe `.env.auth0.local` con `AUTH0_DOMAIN`, `AUTH0_API_AUDIENCE`,
`AUTH0_CLAIMS_NAMESPACE`.

---

### `backup-local`

`pg_dump --format=custom` + cifra con GPG. Guarda en
`./backups/local/<timestamp>/`.

```bash
python -m copiloto_core backup-local
python -m copiloto_core backup-local /path/custom/dir
```

**Requiere**: `gpg`, `pg_dump` instalados. `.secrets/backup_gpg_pubkey.asc`
con la pubkey de cifrado.

---

### `restore-local <backup_dir>`

Restaura un backup local con verificación de integridad.

```bash
python -m copiloto_core restore-local ./backups/local/20260528T120000Z/
```

Por defecto refuse si la DB destino NO está vacía (anti-foot-shoot).

---

### `backup-cloud`

Backup automatizado a S3 con GPG. Diseñado para correr en cron /
systemd timer.

```bash
python -m copiloto_core backup-cloud
```

**Requiere** en `.env`:

```
BACKUP_S3_BUCKET=mi-bucket
BACKUP_S3_ENDPOINT=https://s3.amazonaws.com  # o MinIO
BACKUP_GPG_RECIPIENT=fingerprint_gpg
BACKUP_GPG_PUBKEY_PATH=.secrets/backup_gpg_pubkey.asc
```

---

### `verify-backup`

Verifica integridad GPG de un backup cloud (signature + restore
efímero opcional).

```bash
python -m copiloto_core verify-backup
```

Ver `docs/SEC-009-verifier.md` para el trust model end-to-end.

---

### `smoke-test`

Curl health check de endpoints públicos. Útil post-deploy o en CI.

```bash
python -m copiloto_core smoke-test
# → curls a /v1/branding, /healthz, /metrics (si IP allowlisted)
```

**Exit codes**: `0` todos los checks OK, `1` algún check falló.

---

### `reset-local --yes`

**DESTRUCTIVO**. Borra todos los volúmenes Docker locales (postgres,
redis, minio) — perdés la DB. Requiere `--yes` explícito.

```bash
python -m copiloto_core reset-local --yes
```

Útil cuando querés DB limpia para testear bootstrap from-scratch.

---

## Programmatic API (sin CLI)

Algunos comandos también están expuestos como funciones Python para
testing o automation:

```python
from copiloto_core import (
    apply_platform_schema,
    apply_module_migrations,
    BootstrapError,
    MigrationError,
    generate_project,
    GenerationResult,
)

# Bootstrap
async with conn:
    applied = await apply_platform_schema(
        conn,
        seed=True,
        create_app_user=True,
        app_user='mi_app',
        app_password='secret',
    )

# Migrate
async with conn:
    applied = await apply_module_migrations(conn, mi_modulo)

# Scaffold
result: GenerationResult = generate_project(
    project_name='mi-saas',
    target_dir=Path('/tmp/mi-saas'),
    with_infra=True,
)
```

Las funciones programáticas viven en `copiloto_core.bootstrap`,
`copiloto_core.migrations`, `copiloto_core.scaffolding`. Re-exportadas
del top-level del package (ver `copiloto_core/__init__.py`).

---

## Convenciones generales

- **Idempotencia**: todos los comandos pueden re-correrse sin daño.
  `bootstrap` no re-aplica SQLs ya aplicados, `generate-secrets` no
  pisa valores no-CHANGE_ME, `migrate` solo aplica pendientes.
- **`.env` auto-load**: el CLI carga `.env` del cwd via python-dotenv
  antes de cualquier comando que necesite env vars. NO necesitás
  `source .env` o `export`.
- **Override del shell**: si seteás una env var en el shell, gana
  sobre el `.env` (python-dotenv usa `override=False`).
- **stdin/stdout/stderr**: los comandos heredan los FD del padre.
  Output va al terminal, stdin interactivo funciona. Capturar con
  redirección estándar.
- **Exit codes consistentes**: `0` éxito, `2` config error (params,
  env vars), `3` runtime error (SQL, network, etc.). Los scripts
  bash internos pueden devolver otros códigos — los pasamos
  through.
