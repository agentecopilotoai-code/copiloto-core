# Runbooks operacionales

Esta carpeta contiene los runbooks (.md) que `GET /v1/platform/runbooks` puede
servir y que las alertas Prometheus enlazan en su `annotations.runbook_url`.

En el branch `core` la carpeta arranca vacía (los runbooks de los productos
opt-in viven en cada módulo). El handler `list_runbooks` devuelve un placeholder
hasta que Fase 3 introduzca el reader real desde filesystem o tabla.

## Agregar un runbook

1. Crear `<slug>.md` con el siguiente shape mínimo:

   ```markdown
   # Título legible

   **Categoría:** Infraestructura | Operaciones | Seguridad | …

   ## Síntoma
   …

   ## Diagnóstico
   …

   ## Mitigación
   …

   ## Postmortem
   Link a la postmortem si aplica.
   ```

2. Referenciarlo desde `infra/observability/alerts.yaml` en el
   `annotations.runbook_url` de la regla correspondiente.

3. Cuando Fase 3 esté lista, el endpoint listará automáticamente.
