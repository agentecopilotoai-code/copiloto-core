"""Entrypoint del deployment "core puro" (sin módulos opt-in).

Este módulo construye una instancia FastAPI default con `create_app()`
sin argumentos. Usado SOLO por:

- `docker-compose.yml` del repo del core (CMD uvicorn).
- `Dockerfile` del repo del core (CMD uvicorn).

Los **consumers del paquete** (clientes que construyen su SaaS sobre
el core) NO importan este módulo. Ellos escriben su propio
`main.py`:

    # mi_saas/main.py
    from copiloto_core import create_app, CoreModule, BrandingConfig
    from mi_modulo import module
    app = create_app(modules=[module], branding=BrandingConfig(...))

Y arrancan con `uvicorn mi_saas.main:app`.

# Por qué está separado de copiloto_core/main.py

Antes el side-effect `app = create_app()` vivía en `main.py` mismo.
Eso forzaba a CUALQUIER `import copiloto_core` a evaluar `Settings`
(lo cual exige env vars: DATABASE_URL, JWT_SECRET, etc.). Los
consumers que solo querían importar `CoreModule` / `create_app`
desde sus tests o desde su main propio se rompían ANTES de poder
setear su config.

Mover el side-effect a este módulo separado significa que:
- `import copiloto_core` es lazy: solo evalúa los símbolos importados.
- Los consumers tienen flexibilidad total para componer su app.
- El docker-compose del propio repo del core sigue funcionando
  apuntando a `copiloto_core._runserver:app`.
"""
from copiloto_core.main import create_app

app = create_app()
