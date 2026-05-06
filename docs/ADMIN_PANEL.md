# Admin Panel MVP

El Admin Panel MVP está implementado como una aplicación **React JS + Vite** bajo `admin-panel/`, con componentes, hooks, contexto de autenticación y servicios separados por responsabilidad. El backend mínimo de Auth0/OIDC permanece en `app/admin` para poder usar Authorization Code Flow con el client secret local sin exponer secretos en el navegador.

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

El secreto del cliente se lee desde `.secrets/auth0-admin-client-secret` mediante la ruta declarada en `AUTH0_ADMIN_CLIENT_SECRET_FILE`; nunca se incluye en el bundle React.

## Bootstrap propio

El panel tiene bootstrap dedicado:

```bash
./scripts/bootstrap-admin-panel.sh
```

Qué hace:

1. Instala dependencias npm en `admin-panel/`.
2. Compila el bundle React con `npm --prefix admin-panel run build`.
3. Construye la imagen Docker del servicio `admin-panel` usando `admin-panel/Dockerfile`.

Opciones útiles:

```bash
./scripts/bootstrap-admin-panel.sh --up          # construye y levanta admin-panel
./scripts/bootstrap-admin-panel.sh --skip-docker # solo instala dependencias y compila React localmente
```

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
