"""Módulo Gestión Documental (GD).

Implementa la plataforma institucional de Ventanilla Única, PQRSD, correspondencia
y gestión documental progresiva. Vive bajo el prefijo `gd_*` (schema SQL, rutas,
módulos Python) y reutiliza la identidad/auth/tenancy del producto principal
(`app.users`, `app.tenants`, Auth0, RLS, `app.current_tenant_id()`).

Documentación funcional: docs/gestion documental/{BACKLOG.md, UI_BACKLOG.md,
integracion/, PROGRESO_IMPLEMENTACION.md}.

Schema SQL: infra/postgres/04-gd-schema.sql (y futuros 05-gd-seed.sql, etc.).
"""
