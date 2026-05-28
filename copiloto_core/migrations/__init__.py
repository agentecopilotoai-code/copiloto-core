"""Runner de migrations versionadas para módulos opt-in.

Antes (branch `core` legacy), las migrations del core + módulos se
cargaban via `bootstrap.sh` con `psql -f infra/postgres/*.sql`. Eso
no escala cuando los módulos se distribuyen como wheels pip — sus
archivos `.sql` viven adentro del paquete y `bash` no puede
descubrirlos.

Este runner los descubre desde cada `CoreModule.sql_migrations` y
los aplica idempotentemente con tracking en
`app.schema_migrations(module, version, applied_at, sha256)`.

# Uso

```python
# Auto-aplicar al startup (recomendado para dev/staging):
from copiloto_core import create_app
app = create_app(modules=[mi_modulo], auto_migrate=True)  # Fase 6
```

Para producción mejor opt-out auto y correr explícito en deploy:

```bash
python -m copiloto_core migrate --module=mi_modulo
```

# Convenciones

- Los paths en `CoreModule.sql_migrations` son **relativos al paquete
  Python del módulo** (resueltos via `importlib.resources`).
- Naming: `NNN_descripcion.sql` (ej. `001_init.sql`, `002_add_index.sql`).
  El orden lexicográfico determina el orden de aplicación.
- Cada migration es **toda-o-nada** (envuelta en TX por el runner).
- Una vez aplicada, el SHA-256 queda registrado. Modificar el archivo
  DESPUÉS de aplicarlo levanta `MigrationChecksumMismatchError` —
  forzando workflow correcto (nueva migration > editar la previa).
- La tabla `app.schema_migrations` se auto-crea en la primera corrida.
"""
from copiloto_core.migrations.runner import (
    MigrationChecksumMismatchError,
    MigrationError,
    apply_module_migrations,
    ensure_schema_migrations_table,
)

__all__ = [
    'MigrationChecksumMismatchError',
    'MigrationError',
    'apply_module_migrations',
    'ensure_schema_migrations_table',
]
