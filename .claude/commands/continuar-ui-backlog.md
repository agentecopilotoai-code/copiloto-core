---
description: Implementa la siguiente tarea PENDING del backlog (UI o backend) bajo el flujo local + batching de 6 tareas por PR.
---

Eres responsable de avanzar el roadmap de CopilotoIA. Ejecuta UNA tarea de
principio a fin siguiendo este procedimiento. **No pushees suelto** — el repo
usa un flujo de batching de 6 tareas por PR para minimizar consumo de GitHub
Actions. Ver `memory/feedback_local_ci_flow.md` para el contexto.

## 0. Estado del batch (antes de elegir tarea)

Corre `./scripts/batch-pr.sh status`. Vas a ver:

- `Tareas (commits): X/6` contra `origin/develop`.

Comportamiento según `X`:

- **`X == 0`**: nuevo batch. Si la branch actual es `main`/`develop` o no es
  `claude/batch-*`, crea una con `./scripts/batch-pr.sh next "<tema corto>"`.
  El tema debe describir el conjunto de 6 tareas (p.ej. "influencer backend
  providers", "operations desk split").
- **`1 ≤ X ≤ 5`**: estás en medio de un batch. Continúa en la branch actual.
- **`X == 6`**: el batch está completo. NO empieces otra tarea — corre primero
  `./scripts/batch-pr.sh ship` para abrir el PR, monitorear cloud CI hasta
  verde, y mergear. Después continúa con la siguiente tarea en branch nueva.
- **`X > 6`**: pasaste el límite. `ship --force` o pídele al usuario.

## 1. Selección de la tarea

1. Lee `docs/UI_BACKLOG.md` y `docs/BACKLOG.md` completos.
2. Lee `docs/DONE.md` — es la fuente de verdad de lo ya implementado. No
   repitas trabajo ya `DONE`.
3. Elige la **primera tarea PENDING** respetando dependencias declaradas en
   el item del backlog. Si una tarea tiene subtareas (`UI-006.1`,
   `UI-007.3`...), toma la primera subtarea no implementada.
4. Anuncia qué tarea vas a hacer y por qué es la siguiente.

## 2. Implementación

- Trabaja en la branch del batch actual (`claude/batch-YYYYMMDD-<slug>`).
  Antes de empezar: `git fetch origin develop` y asegúrate de estar al día.
- Si la tarea es una vista UI (`UI-006.x`..`UI-010.x`, `UI-INFLU-###`),
  aplica la **receta 0.bis.1** de `docs/UI_BACKLOG.md`: abre el HTML mapeado
  en 0.bis.3, extrae tokens, inventaría bloques visuales, reusa primitivas
  de `components/ui/` y `components/domain/`.
- Respeta el **Mandato de UI** (sección 1 de `UI_BACKLOG`) y la **Definition
  of Done** (sección 7): ningún archivo > 400 LOC, cero duplicación, tokens
  100% desde `var(--...)`, permisos vía `<RequirePermission>` /
  `usePermissions()`.
- **Sin código legacy.** Si la tarea reemplaza una vista vieja, borra el
  archivo viejo en el mismo commit. No mantengas dos implementaciones.
- Si necesitas tocar el API (`app/api/...`), MANTÉN los parámetros de
  seguridad ya definidos: `authenticate_request`,
  `require_platform_owner` / `require_mfa_for_privileged` según corresponda,
  scoping por tenant y RLS. Nunca relajes una dependencia de seguridad.
- `scripts/bootstrap-admin-panel.sh` es quien compila y monta la UI
  (`npm --prefix admin-panel ci && build` + docker). Cualquier cambio de
  estructura/dependencias del front debe seguir funcionando con ese script.

## 3. Tests

- Agrega tests unitarios de lo fundamental de la tarea (mínimos exigidos
  por la subtarea en el backlog). Front: `vitest` +
  `@testing-library/react` en `admin-panel/`. Backend: `pytest` en `tests/`.
- Si tu tarea baja la cobertura backend bajo 90%, agrega tests adicionales
  hasta restaurarla. El `coverage-gate` de `ci-local-full.sh` exige ≥90%.

## 3.bis Actualización de docs (en el MISMO PR, antes del merge)

Las actualizaciones de docs van en el MISMO commit de la tarea — al
shippear el batch con `./scripts/batch-pr.sh ship` ese commit forma parte
del MISMO PR, antes del merge a develop. Si dejas las docs para un PR
posterior, los commits caen en una branch ya mergeada y el backlog en
`develop` sigue mostrando la tarea como `PENDING`, provocando que la
próxima corrida la repita.

- Actualiza el estado de la tarea en el backlog correspondiente
  (`PENDING` → `DONE`).
- Agrega la entrada en `docs/DONE.md` siguiendo el "Protocolo de
  registro" (consecutivo, fecha, resumen, archivos, validaciones,
  notas/limitaciones, nota de seguridad).

## 5. Validación local (debe pasar TODO antes de commitear)

```
./scripts/ci-local-fast.sh
```

(~30-60s: compile + ruff + pytest unit + admin-panel eslint si node_modules
está instalado).

Si algo falla, arréglalo. **No avances con validación en rojo.**

## 6. Commit

- Commit con mensaje claro: `TASK-XXX — <resumen>` o `UI-XXX — <resumen>`.
- Un commit por tarea (no agrupar 2 tareas en un commit — perdería
  granularidad del batch).
- Incluye en el commit tanto el código/tests como las actualizaciones de
  docs del paso 4.

## 7. Decisión: ¿ship o seguir?

Corre `./scripts/batch-pr.sh status` de nuevo:

- **Si quedan tareas en el batch (X < 6)**: para acá. La siguiente
  invocación del slash command (`/continuar-ui-backlog`) tomará la
  siguiente tarea.
- **Si el batch llegó a 6 (X == 6)**: `./scripts/batch-pr.sh ship` →
  pushea, abre PR. Después:

  ```
  gh pr checks --watch                    # espera hasta que cloud CI termine
  ```

  - **Si cloud CI pasa verde:** `gh pr merge --squash --delete-branch`.
  - **Si cloud CI falla:** lee los logs con `gh run view --log <run-id>`,
    haz un commit fix-up en la misma branch, repushea, y vuelve a
    `gh pr checks --watch`. Auto-fix ilimitado — no pares hasta que pase.
    NUNCA uses `--no-verify` ni `--amend` de commits ya pusheados.

Cuando termines, reporta en 2-3 frases: qué tarea quedó `DONE`, en qué
batch está (X/6), y si el batch se shippeó/mergeó.
