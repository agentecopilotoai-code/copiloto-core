# Admin Panel MVP

El Admin Panel MVP está implementado como una aplicación **React JS + Vite** bajo `admin-panel/`, con componentes, hooks, contexto de autenticación y servicios separados por responsabilidad. El backend mínimo de Auth0/OIDC permanece en `app/admin` para poder usar Authorization Code Flow con el client secret local sin exponer secretos en el navegador. Este backend usa configuración propia y opcional para arrancar aunque no existan las variables obligatorias del core (`DATABASE_URL`, `SERVICE_TOKEN`, WhatsApp o S3); si falta Auth0, la pantalla carga y el login devuelve un error explícito de configuración.

## Estructura React

```text
admin-panel/
├── Dockerfile
├── index.html
├── package.json
├── vite.config.js
└── src/
    ├── App.jsx
    ├── components/
    │   ├── layout/
    │   └── modules/
    ├── context/
    ├── data/
    ├── hooks/
    ├── services/
    └── styles/
```

Patrones aplicados:

- `AuthProvider` centraliza la carga de sesión y expone estado autenticado/anónimo/loading.
- `useActiveModule` encapsula navegación por hash y selección del módulo activo.
- `useTenantOptions` deriva tenants visibles desde los claims namespaced del usuario.
- Componentes de layout (`Sidebar`, `Topbar`, `AdminLayout`) están separados de placeholders funcionales.
- `services/adminSession.js` concentra el acceso HTTP a `/admin/api/session` y las rutas de login/logout.

## Autenticación OIDC/Auth0

El panel usa el backend `app/admin/routes.py` para ejecutar Authorization Code Flow contra Auth0 con la aplicación regular web `copilotoia-admin-web` generada por `scripts/configure-auth0.sh`.

No crea variables paralelas: consume directamente los valores guardados en `.env.auth0.local`:

- `AUTH0_DOMAIN`
- `AUTH0_AUDIENCE` / `AUTH0_API_IDENTIFIER`
- `AUTH0_CLAIMS_NAMESPACE`
- `AUTH0_ADMIN_CLIENT_ID`
- `AUTH0_CALLBACK_URLS`
- `AUTH0_LOGOUT_URLS`
- `AUTH0_ADMIN_CLIENT_SECRET_FILE`

El secreto del cliente se lee desde `.secrets/auth0-admin-client-secret` mediante la ruta declarada en `AUTH0_ADMIN_CLIENT_SECRET_FILE`; nunca se incluye en el bundle React. Para firmar el `state` OAuth el backend usa `JWT_SECRET` cuando está disponible y, si el contenedor se arranca sin `.env`, usa un secreto efímero de proceso para no impedir que el panel cargue. El logout del panel responde al `POST /admin/logout` con redirect `303 See Other` hacia Auth0 para que el navegador llame `GET /v2/logout`; Auth0 no acepta `POST /v2/logout`.

## Bootstrap propio

El panel tiene bootstrap dedicado:

```bash
./scripts/bootstrap-admin-panel.sh
```

Qué hace por defecto:

1. Instala dependencias npm en `admin-panel/`.
2. Compila el bundle React con `npm --prefix admin-panel run build`.
3. Construye la imagen Docker del servicio `admin-panel` usando `admin-panel/Dockerfile`.
4. Levanta el contenedor con `docker compose up -d admin-panel`.
5. Muestra `docker compose ps admin-panel` para confirmar que aparece en Docker.

Opciones útiles:

```bash
./scripts/bootstrap-admin-panel.sh              # compila, construye y levanta admin-panel
./scripts/bootstrap-admin-panel.sh --build-only # compila y construye imagen, pero no levanta contenedor
./scripts/bootstrap-admin-panel.sh --skip-docker # solo instala dependencias y compila React localmente
```

Si ejecutas solo `docker compose build admin-panel`, Docker construye la imagen pero no crea ni arranca el contenedor. Para verlo en Docker necesitas `./scripts/bootstrap-admin-panel.sh` o `docker compose up -d admin-panel`. El servicio `admin-panel` no depende de la salud de la API ni exige `.env`; esto permite abrir `/admin/` y diagnosticar Auth0 aunque el core todavía no esté configurado. El build Vite usa `base: '/admin/'`, por lo que los assets se publican bajo `/admin/assets/*`; el backend conserva una ruta compatible `/assets/*` para builds antiguos cacheados por el navegador. Si tu `.env.auth0.local` fue generado antes de esta corrección, puedes volver a ejecutar `scripts/configure-auth0.sh` para agregar `http://localhost:3000/admin/` a Allowed Logout URLs; mientras tanto el backend usa el primer `AUTH0_LOGOUT_URLS` existente y redirige `/` hacia `/admin/`.

## Comandos de desarrollo

Frontend React en modo dev:

```bash
npm --prefix admin-panel install
npm --prefix admin-panel run dev
```

Backend OIDC/Auth0 del panel:

```bash
python3 -m uvicorn app.admin.main:app --host 0.0.0.0 --port 3000 --reload
```

Build local del frontend:

```bash
npm --prefix admin-panel run build
```

Stack Docker del panel:

```bash
docker compose up --build admin-panel
```

Abrir el panel:

```text
http://localhost:3000/admin/
```

## Conexión con la Core API

El puerto correcto de la **Core API** en esta arquitectura es `8000`; el puerto `3000` pertenece únicamente al backend del Admin Panel (`app/admin`) y sirve el bundle React, login/logout OIDC y endpoints propios bajo `/admin/api/*`. Por eso el frontend no debe llamar endpoints core como `/v1/tenants` contra `http://localhost:3000`.

Para evitar CORS y diferencias entre Docker y ejecución local, el Admin Panel expone un proxy autenticado en:

```text
/admin/api/core/v1/*
```

El proxy reenvía la sesión del admin hacia la Core API configurada por `ADMIN_CORE_API_BASE_URL`:

- En Docker Compose se usa `http://api:8000`, que es el nombre del servicio interno de la Core API.
- En ejecución local directa el valor por defecto es `http://127.0.0.1:8000`.

El endpoint `/admin/api/session` informa al frontend `api.baseUrl = /admin/api/core/v1`, y los servicios React construyen las llamadas desde ese valor en vez de asumir `/v1` en el mismo origen.


## Onboarding self-service de tenant

Cuando el usuario autenticado no trae `tenant_id` en sus claims, el panel no crea un tenant falso ni muestra selector de tenants. En su lugar muestra una tarjeta central **Crear tenant**. Ese flujo llama `POST /admin/api/core/v1/tenant-signup`, que crea el tenant, registra/actualiza el usuario autenticado en `app.users`, le asigna el rol `owner` en `app.user_tenant_roles` y deja auditoría `tenant.self_service_created`.

Después de crear el tenant, el panel usa el UUID real devuelto por la API como tenant activo y envía `X-Tenant-Id` para guardar settings. La Core API valida ese acceso contra `app.user_tenant_roles`, por lo que no depende de un claim `tenant_id` recién emitido por Auth0 para completar el wizard inicial. En cargas posteriores, el panel consulta `GET /admin/api/core/v1/me/tenants` para reconstruir el tenant activo desde la membresía guardada en base de datos mientras Auth0 todavía no emite el claim.

## Funcionalidad incluida

- Pantalla React de login con Auth0/OIDC.
- Callback OIDC en `/callback` y `/admin/callback` para compatibilidad con callbacks locales.
- Sesión HTTP-only de servidor para el MVP.
- Layout base React con selector de tenant a partir de claims namespaced (`tenant_id` y `tenant_slug`).
- Navegación entre módulos placeholder:
  - Tenant Setup
  - WhatsApp
  - Knowledge Studio
  - Operations Desk
  - Audit

## Limitaciones intencionales del MVP

- Las sesiones viven en memoria del proceso; en producción deben moverse a Redis o almacenamiento equivalente.
- Los módulos son placeholders navegables; las tareas siguientes del backlog conectan formularios y endpoints reales.
- El selector de tenant usa el tenant emitido por Auth0 en claims; gestión multi-tenant avanzada queda para tareas posteriores.
