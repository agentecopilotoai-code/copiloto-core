# Branch protection — política de merge

> Esta política se compone de **3 piezas**: gates de coverage en CI, branch
> protection rules en GitHub, y un workflow de auto-merge con cool-down de
> 5 min. Las primeras dos son obligatorias; el auto-merge es opt-in por PR.

## 1. Gates de coverage en CI (ya configurados)

### Backend — `pytest --cov-fail-under=90`

Job: `API — coverage ≥90% (gate de merge)` en `.github/workflows/ci.yml`.

- Levanta Postgres ephemeral, corre **todo** el suite (unit + E2E) con
  `pytest --cov=app --cov-fail-under=90`.
- Si el agregado total cae bajo **90%**, el job sale con exit 1 → check rojo
  → merge bloqueado.

### Frontend — vitest `thresholds: { lines: 85, statements: 85 }`

Archivo: `admin-panel/vitest.config.js`. El job `Admin Panel — install,
lint & build` ya corre `npm run test:coverage` → vitest evalúa los thresholds
y sale con exit 1 si el agregado cae bajo **85%**.

Umbrales globales en `vitest.config.js`:

```js
thresholds: {
  lines: 85, statements: 85,
  functions: 75, branches: 75,
  'src/components/ui/**': { lines: 85, ... },
  'src/permissions/**':   { lines: 85, ... },
  'src/services/**':      { lines: 85, ... },
  'src/hooks/**':         { lines: 85, ... },
  'src/features/**':      { lines: 80, ... },
}
```

## 2. Branch protection rules — configurar en GitHub

**Lo tienes que hacer una vez en la UI o con `gh api`** (requiere permisos
admin del repo).

### Via UI

`Settings → Branches → Branch protection rules → Add rule`:

- **Branch name pattern**: `main`
- ☑ **Require a pull request before merging**
  - ☑ Require approvals: **1**
  - ☑ Dismiss stale approvals when new commits are pushed
  - ☑ Require review from Code Owners (opcional, requiere `.github/CODEOWNERS`)
- ☑ **Require status checks to pass before merging**
  - ☑ Require branches to be up to date before merging
  - **Status checks required**:
    - `API — compile, lint & test`
    - `API — journey E2E (Postgres ephemeral)`
    - `API — coverage ≥90% (gate de merge)`
    - `Admin Panel — install, lint & build`
- ☑ **Require conversation resolution before merging**
- ☑ **Do not allow bypassing the above settings** (incluye admins)
- ☐ Require linear history (opcional)
- ☐ Require deployments to succeed (no aplica)

Repetir para `develop` con los mismos checks.

### Via `gh api` (reproducible)

```bash
gh api -X PUT /repos/ravitstudioapps/CopilotoIA/branches/main/protection \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "API — compile, lint & test",
      "API — journey E2E (Postgres ephemeral)",
      "API — coverage ≥90% (gate de merge)",
      "Admin Panel — install, lint & build"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "required_approving_review_count": 1
  },
  "restrictions": null,
  "required_conversation_resolution": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF
```

## 3. Auto-merge con cool-down de 5 minutos

Workflow: `.github/workflows/auto-merge.yml`.

### Cómo activar el auto-merge en un PR

1. PR pasa CI completamente (4 checks verdes).
2. PR tiene al menos 1 review aprobado.
3. **Agregar la label `auto-merge`** al PR.
4. El workflow se dispara, **espera 5 minutos** (cool-down para reviewers
   tardíos), y re-verifica:
   - PR sigue abierto, no draft, mergeable.
   - Label `auto-merge` no se removió.
   - `mergeable_state == 'clean'` (CI sigue verde, branch up-to-date).
   - **Ningún reviewer requested changes** durante los 5 min.
   - Al menos 1 reviewer aprobó.
   - **No hubo nuevos commits durante el cool-down** (push reciente reinicia).
5. Si todo cumple → `merge_method: squash` → comenta `✅ Auto-merged`.
6. Si algo falla → comenta `🚫 Auto-merge skipped: <razón>` y espera el
   próximo evento (otro push, review, o re-disparo del check_suite).

### Cómo cancelar el auto-merge

- Remover la label `auto-merge`.
- Hacer un nuevo push (reinicia el cool-down).
- Dejar un review con `Request changes`.

### Eventos que disparan el workflow

- `pull_request.labeled` (cuando alguien agrega la label)
- `pull_request.synchronize` (nuevo push)
- `pull_request_review.submitted` (alguien dio review)
- `check_suite.completed` (CI terminó)
- `workflow_dispatch` (manual con número de PR)

### Política end-to-end

```
PR creado → CI corre → 1+ approvals → label `auto-merge` agregada
   ↓
Workflow auto-merge se dispara → sleep 300s
   ↓
Re-verifica:
  - CI sigue verde
  - No 'changes-requested'
  - Sin push reciente (≥5 min sin updates)
  - Label `auto-merge` sigue presente
   ↓
Squash-merge automático → comentario de éxito
```

## Crear la label `auto-merge` una vez

```bash
gh label create auto-merge \
  --color "0E8A16" \
  --description "Activate the 5-min cool-down auto-merger" \
  --force
```

## Operaciones comunes

| Operación | Comando |
|-----------|---------|
| Verificar protection actual | `gh api /repos/ravitstudioapps/CopilotoIA/branches/main/protection` |
| Forzar re-evaluación de auto-merge | Workflow manual: `gh workflow run auto-merge.yml -f pr_number=83` |
| Ver estado de coverage del PR | Comments del job `API — coverage` |
| Bajar temporal el umbral (emergencia) | Editar `--cov-fail-under` en CI + abrir PR con razón |

## Cómo subir los umbrales en el tiempo

Mantener un linotipo en `docs/DONE.md` con el coverage histórico. Cuando
suba sostenidamente (por ejemplo backend 92% → 94% por 2 semanas), bumpear:

- `--cov-fail-under=92` en CI
- Bumpear los thresholds globales en `vitest.config.js`

Nunca bajar — solo subir.
