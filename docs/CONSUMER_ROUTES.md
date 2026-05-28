# Mapa de rutas — quién sirve qué en un proyecto consumer

Esta guía explica **qué URL la sirve quién** cuando construís un SaaS
sobre `copiloto-core`. Es lo que necesitás saber para no chocar
handlers entre el core, tu landing, tu dashboard, y tus módulos.

> Para crear un proyecto desde cero, ver [QUICKSTART.md](QUICKSTART.md).
> Para el catálogo de comandos CLI, ver [CLI.md](CLI.md).

---

## Mapa default (con `--with-infra` y `admin_panel=False`)

```
┌──────────────────────────────────────────────────────────────────────┐
│  http://localhost:8000                                               │
│                                                                      │
│  /                            → TU LANDING (templates/landing.html) │
│  /dashboard                   → TU DASHBOARD (auth-required)         │
│                                                                      │
│  /admin/login                 → CORE: inicia OAuth (Auth0)           │
│  /admin/callback              → CORE: recibe callback OAuth          │
│  /admin/logout (POST)         → CORE: termina sesión                 │
│  /admin/api/session (GET)     → CORE: info del user logueado (JSON)  │
│  /admin/api/core/* (proxy)    → CORE: BFF proxy al backend interno   │
│  /admin/                      → 404 (admin SPA OFF por default)      │
│  /admin/{cualquier-otra}      → 404                                  │
│                                                                      │
│  /v1/branding                 → CORE: branding del deployment (JSON) │
│  /v1/me                       → CORE: info del user (auth req)       │
│  /v1/tenants/*                → CORE: tenant management              │
│  /v1/platform/*               → CORE: platform-owner-only endpoints  │
│  /v1/<tu-modulo>/*            → TU MÓDULO (routers.py)               │
│                                                                      │
│  /v1/invitations/{token}      → CORE: redemption de invitations      │
│  /i/{token}                   → CORE: landing pública de invitation  │
│                                                                      │
│  /metrics                     → CORE: Prometheus (IP-allowlisted)    │
│  /openapi.json                → FastAPI: OpenAPI spec                │
│  /docs                        → FastAPI: Swagger UI                  │
└──────────────────────────────────────────────────────────────────────┘
```

**TU CÓDIGO en azul, CORE en gris**: el consumer típicamente solo toca
`/` y `/dashboard` (en `templates/`), y `/v1/<modulo>/*` (en
`<modulo>/routers.py`). Todo lo demás es transparente.

---

## Mapa con `admin_panel=True`

Si en `main.py` activás el SPA del admin del core
(`create_app(..., admin_panel=True)`):

```
+ /admin/                       → CORE: React SPA del admin
+ /admin/{spa_path:path}        → CORE: SPA fallback
+ /admin/assets/{path:path}     → CORE: Vite assets
+ /favicon.ico                  → CORE: favicon
```

**Desde v1.6.0**: el wheel ya trae el SPA pre-buildeado dentro
(`copiloto_core/admin/static/dist/`, ~556KB). NO requiere Node ni
clonar el repo del core — `pip install copiloto-core` + `admin_panel=True`
es suficiente.

> Para versiones < 1.6.0, había que clonar el repo del core,
> `npm run build` y copiar manualmente. v1.6.0 lo automatiza en el
> `release.sh` del core, que corre el build de Vite y commitea el dist
> como parte del release commit antes del tag.

> **Most consumers don't need the core's admin**. Tu landing +
> dashboard + módulo te dan todo. El admin del core es para
> superadmins gestionando tenants, no para los users finales de
> tu SaaS.

---

## Flujo de login (lo que pasa cuando el user clickea "Iniciar sesión")

```
1. User en TU landing http://localhost:8000/
   └─ Click en "Iniciar sesión" (href="/admin/login")

2. GET /admin/login
   └─ CORE redirect a Auth0:
      https://tu-tenant.auth0.com/authorize?response_type=code&...

3. User se loguea en Auth0 (puede ser MFA si está activado)

4. Auth0 redirect a callback:
   GET /admin/callback?code=...&state=...
   └─ CORE valida code+state, intercambia por id_token + access_token
   └─ CORE setea cookie de sesión (HTTP-only, SameSite=Lax)
   └─ CORE redirect al `redirect_uri` que el flow inició (puede ser /dashboard)

5. User aterriza en /dashboard
   └─ TU handler con Depends(authenticate_request)
   └─ CORE valida cookie → resuelve user → permite request
   └─ TU dashboard.html se sirve

6. Cliente JS hace fetch /admin/api/session
   └─ CORE devuelve {email, sub, tenant_id, roles, ...}
   └─ TU JS muestra "Hola <email>"
```

**Logout**:
```
1. User clickea botón "Cerrar sesión" en /dashboard
2. JS hace POST /admin/logout (con cookie)
3. CORE invalida la sesión + borra cookie
4. JS redirect a /
```

---

## Cómo cambiar a dónde redirige el login

Por default, el core redirige al `redirect_uri` que el OAuth flow
empezó con. Si tu landing inicia el flow con
`/admin/login?return_to=/dashboard`, el callback redirige a
`/dashboard`. Si pone `return_to=/onboarding`, va ahí.

Editá `templates/landing.html`:

```html
<!-- en vez de simple href="/admin/login" -->
<a href="/admin/login?return_to=/dashboard" class="login-btn">Iniciar sesión</a>
```

> **Importante**: `return_to` debe matchear una URL allowlisted en la
> config Auth0 (Allowed Callback URLs en el dashboard). Sino el core
> aborta el callback como anti-open-redirect. Ver
> [AUTH0.md](AUTH0.md) § Configurar redirect URIs.

---

## Cómo agregar más páginas del consumer

Editá `<project>/main.py` y registrá handlers:

```python
@app.get('/onboarding', response_class=HTMLResponse)
async def onboarding(_actor=Depends(authenticate_request)) -> str:
    # ... tu lógica de onboarding
    return Path('templates/onboarding.html').read_text()

@app.get('/billing', response_class=HTMLResponse)
async def billing(actor=Depends(authenticate_request)) -> str:
    # actor tiene .email, .sub, .tenant_id, .roles
    if 'admin' not in actor.roles:
        raise HTTPException(403, 'admin only')
    return Path('templates/billing.html').read_text()
```

Para endpoints API (no UI), usá tu módulo (`<modulo>/routers.py`)
en vez de `main.py` — eso mantiene la separación core ↔ módulos
clara y permite que migraciones SQL del módulo se trackeen separadas.

---

## Cómo agregar más módulos opt-in

Cada módulo se monta automáticamente bajo `/v1/<code>/*`. Para
agregar uno nuevo:

1. Crear un paquete Python con la convención de
   [EXTENDING.md](EXTENDING.md).
2. Importarlo en `main.py` y agregarlo a la lista:

```python
from satguajira_modulo import module as modulo1
from otro_modulo import module as modulo2

app = create_app(
    modules=[modulo1, modulo2],
    branding=BrandingConfig(product_name="SAT Guajira"),
)
```

3. Sus endpoints serán accesibles en:
   - `/v1/satguajira-modulo/*` (kebab del code)
   - `/v1/otro-modulo/*`

---

## Cómo customizar tu landing/dashboard

Los archivos `templates/landing.html` y `templates/dashboard.html`
son **HTML+CSS+JS vanilla** sin framework. Editalos directo:

- **Branding visual**: cambiá el CSS gradient/colores en el `<style>`.
- **Logo**: agregá `<img src="/static/logo.svg">` y mounteá `/static`
  con `app.mount("/static", StaticFiles(...))` en main.py.
- **Dashboard widgets**: el JS al final del dashboard hace fetch a
  `/admin/api/session` — agregá más fetches a tus endpoints del módulo
  para mostrar data.
- **React/Vue/Svelte**: reemplazá `templates/dashboard.html` con un
  HTML que cargue tu bundle Vite. El handler de Python no cambia.

---

## ¿Qué NO podés cambiar (sin tocar el core)?

- **Paths bajo `/admin/api/*`**: son del BFF interno del core para
  el admin panel. No los pises desde tu app.
- **Paths bajo `/v1/platform/*`**: endpoints platform-owner-only.
  Solo el equipo del core los modifica.
- **`/v1/branding`, `/v1/me`, `/v1/tenants/*`**: API contractual del
  core, parte del semver public surface.
- **`/admin/login`, `/admin/callback`, `/admin/logout`**: el flow
  OAuth tiene state machine compleja (PKCE, nonce, anti-CSRF). No
  reemplaces estos endpoints — usalos.

Si tenés un caso donde necesitás extender el core con un endpoint
nuevo bajo `/v1/*` o `/admin/*`, abrí una issue en el repo del
core. La extensión vía `CoreModule` es la API canónica.
