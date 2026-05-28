# Quickstart — crear un SaaS sobre `copiloto-core` desde cero

Esta guía te lleva de **directorio vacío** a **SaaS corriendo en
`http://localhost:8000`** en ~5 minutos. Probado en macOS Sequoia
con Python 3.12+, Docker Desktop, y `gh` CLI.

> Para entender QUÉ estás construyendo, leé primero
> [ARCHITECTURE.md](../ARCHITECTURE.md). Para extender el core con
> tus propios módulos, [EXTENDING.md](EXTENDING.md). Para el
> catálogo completo de comandos CLI, [CLI.md](CLI.md).

---

## 0. Pre-checks

Antes de empezar, confirmá que tu máquina tiene lo necesario:

```bash
# Python 3.12+ instalado
python3 --version
# Esperado: Python 3.12.x o superior

# Docker Desktop corriendo
docker info > /dev/null 2>&1 && echo "✓ docker OK" || echo "✗ abrí Docker Desktop"

# gh CLI logueado con cuenta que tiene acceso al repo del core
gh auth status 2>&1 | grep "agentecopilotoai-code" && echo "✓ gh OK" || \
  echo "✗ necesitás gh auth login con cuenta agentecopilotoai-code"

# gh como credential helper de git (para que pip pueda clonar HTTPS)
gh auth setup-git
```

Si alguno falla, frená y arreglalo antes de seguir.

**¿Por qué `gh auth setup-git`?** El core vive en un repo privado.
`pip install` necesita credenciales para clonarlo. La forma más
limpia es delegar la auth en `gh` (que ya tiene tu token); así
evitás meter tokens en URLs o claves SSH específicas del org.

---

## 1. Venv en un directorio limpio

```bash
# Donde quieras tener el proyecto
mkdir -p ~/Documents/GitHub/hello/
cd ~/Documents/GitHub/hello/

# Si tenés algo viejo, nukealo (vol docker + carpeta)
docker compose -f satguajira/docker-compose.yml down -v 2>/dev/null
rm -rf satguajira .venv

# Venv nuevo + activar
python3 -m venv .venv
source .venv/bin/activate

# Verificar que estás en el venv
which python
# Esperado: /Users/<vos>/Documents/GitHub/hello/.venv/bin/python
```

> **macOS specific**: `python` (sin el `3`) NO existe en macOS reciente.
> Siempre usá `python3` para crear el venv. Una vez activado, dentro
> del venv `python` apunta al binario correcto.

---

## 2. Instalar copiloto-core

```bash
pip install --upgrade pip   # opcional, evita el notice
pip install "copiloto-core @ git+https://github.com/agentecopilotoai-code/copiloto-core.git@v1.4.0"

# Confirmar
python -m copiloto_core version
# Esperado: copiloto-core 1.4.0
```

---

## 3. Generar el proyecto consumer

```bash
python -m copiloto_core new-project satguajira --with-infra
cd satguajira
pip install -e ".[dev]"
```

Esto genera:

```
satguajira/
├── pyproject.toml            # pin a copiloto-core@v1.4.0
├── .env.example              # plantilla con CHANGE_ME placeholders
├── .gitignore                # excluye .env, .secrets/
├── README.md                 # quickstart específico del proyecto
├── docker-compose.yml        # postgres + redis + minio
├── scripts/
│   └── dev-up.sh             # compose up + bootstrap + migrate + uvicorn
├── .secrets/.gitkeep         # placeholder para secretos locales
├── satguajira/
│   ├── __init__.py
│   └── main.py               # app = create_app(modules=[...], branding=...)
└── satguajira_modulo/
    ├── __init__.py           # exporta `module = CoreModule(...)`
    ├── routers.py            # /v1/satguajira-modulo/health + /items
    └── migrations/
        └── 001_init.sql      # schema RLS-ready
```

---

## 4. Generar secrets en `.env`

```bash
python -m copiloto_core generate-secrets
```

Esto reemplaza los `CHANGE_ME` del `.env.example` con valores random
seguros y escribe `.env` con permisos `600` (solo owner puede leer):

- `APP_DB_PASSWORD` — password del rol `copiloto_app` (runtime).
- `POSTGRES_PASSWORD` — password del rol `postgres` (admin).
- `JWT_SECRET` — secreto para firmar tokens internos (64 chars).
- `SERVICE_TOKEN` — auth entre servicios internos (48 chars).
- `S3_SECRET_ACCESS_KEY` — credencial MinIO (32 chars).

Confirmar:

```bash
grep -E "^(APP_DB_PASSWORD|POSTGRES_PASSWORD|JWT_SECRET|SERVICE_TOKEN|S3_SECRET_ACCESS_KEY)=" .env
```

> **Importante**: `generate-secrets` es **idempotente** y **preserva**
> hostnames, nombres de DB, bucket, etc. Solo reemplaza valores
> exactos `CHANGE_ME`. Si lo corrés dos veces, la segunda no hace
> nada (no hay CHANGE_ME pendientes).

---

## 5. Levantar todo en un comando

```bash
./scripts/dev-up.sh
```

`dev-up.sh` orquesta:

1. **`docker compose up -d`** — postgres (pgvector), redis, minio.
2. **Espera a postgres healthy** — con un loop de hasta 30s.
3. **`python -m copiloto_core bootstrap --create-app-user`**:
   - Crea el rol `copiloto_app` con `APP_DB_PASSWORD`.
   - Aplica `10-core.sql` (schema `app.*`: tenants, users, rbac,
     audit, sessions, rate-limit, ai providers, modules).
   - Aplica `20-seed.sql` (tenant demo `demo`).
   - Aplica grants finales sobre `app.*` para `copiloto_app`.
4. **`python -m copiloto_core migrate --module=satguajira_modulo`** —
   aplica las migrations del módulo demo (`001_init.sql`).
5. **`uvicorn satguajira.main:app --reload --host 0.0.0.0 --port 8000`** —
   arranca la app y queda escuchando.

Output esperado:

```
→ Levantando docker compose…
 ✔ Container satguajira-postgres-1  Started
 ✔ Container satguajira-redis-1     Started
 ✔ Container satguajira-minio-1     Started
→ Esperando a que postgres esté healthy…
  ✓ postgres listo
→ Aplicando platform schema del core…
✓ Platform schema aplicado (2 archivos):
  - 10-core.sql
  - 20-seed.sql
  rol runtime: copiloto_app (creado o ya existía)
→ Aplicando migrations del módulo satguajira_modulo…
Aplicadas 1 migrations para satguajira_modulo:
  - 001_init
→ Arrancando uvicorn (Ctrl+C para detener)…
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

**Cuando ves `Uvicorn running on http://0.0.0.0:8000`, el SaaS está corriendo.**

Dejá esa terminal abierta.

---

## 6. Verificar

En **otra terminal**:

```bash
curl -s http://localhost:8000/v1/branding | python3 -m json.tool
# Esperado: JSON con product_name "CopilotoIA" + colores hex

curl -s http://localhost:8000/v1/satguajira-modulo/health | python3 -m json.tool
# Esperado: {"status": "ok", "module": "satguajira_modulo"}
```

Si los dos devuelven JSON sin error, **estás corriendo un SaaS
multi-tenant con auth0/RBAC/RLS/audit/IA dispatch listos para
extender**.

---

## 7. (Opcional) Configurar Auth0

Para login real, ver [AUTH0.md](AUTH0.md). Para dev sin auth, lo
de arriba es suficiente — los endpoints sin auth (`/v1/branding`,
`/health`) funcionan; los que requieren auth (los que tienen
`Depends(authenticate_request)`) van a fallar con 401 hasta que
configures Auth0.

---

## Troubleshooting

| Error | Causa | Fix |
|---|---|---|
| `command not found: pip` o `permission denied: python` | El venv no está activo | `source .venv/bin/activate` |
| `port 5432 already in use` | Otro postgres corriendo | `docker ps`, `docker stop <id>` |
| `Cannot connect to Docker daemon` | Docker Desktop no arrancó | Abrí Docker Desktop, esperá ~30s |
| `Permission denied (publickey)` al `pip install` | SSH key no tiene acceso al org | Usá HTTPS + `gh auth setup-git` |
| `Repository not found` al `pip install` | Mismo problema de access | Ver punto anterior |
| `bash: ./scripts/dev-up.sh: Permission denied` | Script sin x-bit (raro, scaffolder lo pone) | `chmod +x scripts/dev-up.sh` |
| `gaierror: nodename nor servname provided` | DATABASE_URL usa hostname docker pero corrés desde host | Verificá que .env tenga `@localhost:` no `@postgres:` |
| `InvalidPasswordError: ... "copiloto_admin"` | .env contaminado de versión vieja | Borrar `.env`, regenerar con `generate-secrets` |
| `permission denied for schema app` en migrate | Bug v1.3.5 fixado en v1.3.6 | Upgrade a v1.4.0+ |
| `ValidationError: service_token Field required` | Falta SERVICE_TOKEN en .env | `generate-secrets` (v1.3.5+ lo agrega) |

Si nada de esto matchea, levantá un issue en
https://github.com/agentecopilotoai-code/copiloto-core/issues con
el output completo.

---

## Limpiar todo cuando termines

```bash
# Ctrl+C en la terminal del uvicorn

# Apagar la infra (mantiene datos)
docker compose down

# O nuke total (pierde la DB)
docker compose down -v

# Para borrar todo el proyecto y empezar de cero
cd ..
rm -rf satguajira
```

---

## Próximos pasos

- **Construir tu primer módulo**: [EXTENDING.md](EXTENDING.md).
- **Configurar Auth0 real**: [AUTH0.md](AUTH0.md).
- **Catálogo completo de comandos**: [CLI.md](CLI.md).
- **Arquitectura del core**: [../ARCHITECTURE.md](../ARCHITECTURE.md).
