---
description: Implementa la siguiente tarea PENDING del backlog de UI, crea el PR, y si CI pasa la mergea a develop.
---

Eres responsable de avanzar el rediseño de UI de CopilotoIA. Ejecuta UNA tarea del
backlog de UI de principio a fin siguiendo este procedimiento. No te saltes pasos.

## 1. Selección de la tarea

1. Lee `docs/UI_BACKLOG.md` completo.
2. Lee `docs/DONE.md` — es la fuente de verdad de la lógica del sistema, los
   parámetros de seguridad y lo ya implementado. No repitas trabajo ya `DONE`.
3. Elige la **primera tarea con estado `PENDING`** respetando el orden de
   ejecución de la sección 6 del backlog y sus dependencias. Si una tarea tiene
   subtareas (`UI-006.1`, `UI-007.3`...), toma la primera subtarea no implementada.
4. Anuncia qué tarea vas a hacer y por qué es la siguiente.

## 2. Implementación

- Trabaja siempre en la rama `claude/implement-ui-backlog-kuv9g` (créala desde
  `develop` si no existe). Antes de empezar: `git fetch origin develop` y
  asegúrate de estar al día.
- Si la tarea es una vista (`UI-006.x`..`UI-010.x`), aplica la **receta 0.bis.1**
  del backlog: abre el HTML mapeado en 0.bis.3, extrae tokens, inventaría bloques
  visuales, reusa primitivas de `components/ui/` y `components/domain/`.
- Respeta el **Mandato de UI** (sección 1) y la **Definition of Done** (sección 7):
  ningún archivo > 400 LOC, cero duplicación, tokens 100% desde `var(--...)`,
  permisos vía `<RequirePermission>` / `usePermissions()`.
- **Sin código legacy.** Si la tarea reemplaza una vista vieja, borra el archivo
  viejo en el mismo commit. No mantengas dos implementaciones en paralelo.
- Si necesitas tocar el API (`app/api/...`), MANTÉN los parámetros de seguridad
  ya definidos en el servidor: `authenticate_request`, `require_platform_owner`
  / `require_mfa_for_privileged` según corresponda, scoping por tenant y RLS.
  Nunca relajes una dependencia de seguridad existente.
- Recuerda que `scripts/bootstrap-admin-panel.sh` es quien compila y monta la UI
  (`npm --prefix admin-panel ci && build` + docker). Cualquier cambio de
  estructura/dependencias del front debe seguir funcionando con ese script.

## 3. Tests

- Agrega tests unitarios de lo fundamental de la tarea (mínimos exigidos por la
  subtarea en el backlog). Front: `vitest` + `@testing-library/react` en
  `admin-panel/`. Backend: `pytest` en `tests/`.

## 4. Validación local (debe pasar TODO antes de continuar)

```
npm --prefix admin-panel run lint
npm --prefix admin-panel run build
npm --prefix admin-panel test
```

Si tocaste backend: `ruff check app` y `pytest` de los módulos afectados.
Si algo falla, arréglalo. No avances con validación en rojo.

## 5. Commit y PR

- Commit con mensaje claro y descriptivo (`UI-XXX — <resumen>`).
- `git push -u origin claude/implement-ui-backlog-kuv9g` (reintenta con backoff
  2s/4s/8s/16s solo ante errores de red).
- Crea el PR hacia `develop` con las tools de GitHub MCP
  (`mcp__github__create_pull_request`) — repo `vmantilla/copilotoia`. En el
  cuerpo: tarea, alcance, validaciones ejecutadas, y screenshots lado a lado
  HTML vs React si es una vista (criterio 0.bis.4).

## 6. Verificar CI y mergear

- Espera y verifica el estado de CI del PR (`mcp__github__pull_request_read` con
  los checks).
- **Si CI pasa en verde:** mergea el PR a `develop`
  (`mcp__github__merge_pull_request`).
- **Si CI falla:** investiga, corrige, vuelve a pushear (commit NUEVO, nunca
  `--amend`) y re-verifica. No mergees con CI en rojo.

## 7. Cierre de la tarea

- Actualiza `docs/UI_BACKLOG.md`: estado de la tarea → `DONE`.
- Agrega la entrada en `docs/DONE.md` siguiendo el "Protocolo de registro"
  (consecutivo, fecha, resumen, archivos, validaciones, notas/limitaciones y la
  nota de seguridad).
- Commitea y pushea esa actualización de docs.

Cuando termines, reporta en 2-3 frases: qué tarea quedó `DONE`, si se mergeó, y
cuál es la siguiente tarea `PENDING` del backlog.
