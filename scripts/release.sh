#!/usr/bin/env bash
# release.sh — bump version + tag + push para `copiloto-core`.
#
# Distribución sin PyPI (decisión Fase 9 audit#5): los módulos consumen
# el core como dep git+ssh contra un tag específico:
#
#   [project]
#   dependencies = [
#     "copiloto-core @ git+ssh://git@github.com/.../copiloto-core.git@v1.0.0",
#   ]
#
# Este script:
#   1. Verifica que el working tree está limpio y en branch protegido.
#   2. Verifica que la suite de tests pasa.
#   3. Verifica que la version del pyproject + copiloto_core/__init__.py
#      están sincronizadas.
#   4. Crea el tag vX.Y.Z y lo pushea al remote.
#
# Uso:
#   ./scripts/release.sh                     # tag de la version actual
#   ./scripts/release.sh --bump=patch        # 1.0.0 → 1.0.1
#   ./scripts/release.sh --bump=minor        # 1.0.0 → 1.1.0
#   ./scripts/release.sh --bump=major        # 1.0.0 → 2.0.0
#   ./scripts/release.sh --dry-run           # no push, solo printea acciones
#
# Convención semver:
#   MAJOR (1.x→2.x): breaking change en API pública (copiloto_core/__init__.py)
#                    debe pre-anunciarse con DeprecationWarning ≥ 2 minors antes.
#   MINOR (1.0→1.1): añade símbolos. Firmas existentes compat.
#   PATCH (1.0.0→1.0.1): bugfixes internos.
#
# Después de tagear, los módulos pueden bumpear su pin:
#   sed -i 's/copiloto-core.git@v1\.0\.0/copiloto-core.git@v1.0.1/g' pyproject.toml
set -euo pipefail

REPO_REMOTE="${REPO_REMOTE:-copiloto-core}"
PROTECTED_BRANCH="${PROTECTED_BRANCH:-main}"
DRY_RUN=0
BUMP=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bump=patch|--bump=minor|--bump=major)
            BUMP="${1#--bump=}"; shift ;;
        --dry-run)
            DRY_RUN=1; shift ;;
        --help|-h)
            head -36 "$0" | tail -34 | sed 's|^# \{0,1\}||'
            exit 0 ;;
        *)
            echo "ERROR: argumento desconocido: $1" >&2
            exit 2 ;;
    esac
done

# ── 1. Working tree limpio ──
if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: working tree no está limpio. Comiteá o descartá cambios antes." >&2
    git status --short >&2
    exit 1
fi

# ── 2. Branch correcto ──
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$CURRENT_BRANCH" != "$PROTECTED_BRANCH" ]]; then
    echo "ERROR: tagging release solo desde branch '$PROTECTED_BRANCH' (estás en '$CURRENT_BRANCH')." >&2
    echo "  Override: PROTECTED_BRANCH=<branch> $0 ..." >&2
    exit 1
fi

# ── 3. Tests verdes ──
echo "▶ Corriendo suite de tests..."
if ! python -m pytest --quiet --tb=line 2>&1 | tail -3; then
    echo "ERROR: tests fallan. Arregla antes de tagear." >&2
    exit 1
fi
echo "✓ Tests OK"

# ── 4. Leer version actual del pyproject + __init__.py ──
PYPROJECT_VERSION="$(grep -E '^version *= *' pyproject.toml | head -1 \
    | sed -E 's/version *= *"([^"]+)"/\1/')"
INIT_VERSION="$(grep -E "^__version__ *= *" copiloto_core/__init__.py \
    | sed -E "s/__version__ *= *['\"]([^'\"]+)['\"]/\1/")"

if [[ "$PYPROJECT_VERSION" != "$INIT_VERSION" ]]; then
    echo "ERROR: version desync entre pyproject.toml ($PYPROJECT_VERSION) y __init__.py ($INIT_VERSION)" >&2
    exit 1
fi

CURRENT_VERSION="$PYPROJECT_VERSION"
echo "▶ Version actual: $CURRENT_VERSION"

# ── 5. Bump si se pidió ──
if [[ -n "$BUMP" ]]; then
    IFS='.' read -r MAJOR MINOR PATCH <<<"$CURRENT_VERSION"
    case "$BUMP" in
        patch) PATCH=$((PATCH + 1)) ;;
        minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
        major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
    esac
    NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
    echo "▶ Bump $BUMP: $CURRENT_VERSION → $NEW_VERSION"

    if [[ $DRY_RUN -eq 0 ]]; then
        # Update pyproject.toml
        sed -i.bak -E "s/^version *= *\"[^\"]+\"/version = \"$NEW_VERSION\"/" pyproject.toml
        rm -f pyproject.toml.bak
        # Update __init__.py
        sed -i.bak -E "s/__version__ *= *['\"][^'\"]+['\"]/__version__ = '$NEW_VERSION'/" copiloto_core/__init__.py
        rm -f copiloto_core/__init__.py.bak

        git add pyproject.toml copiloto_core/__init__.py
        git commit -m "chore: bump version → $NEW_VERSION"
    fi
    TAG_VERSION="$NEW_VERSION"
else
    TAG_VERSION="$CURRENT_VERSION"
fi

TAG="v${TAG_VERSION}"

# ── 6. Verificar que el tag no exista ya ──
if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "ERROR: tag $TAG ya existe en local. Borralo con 'git tag -d $TAG' si querés re-tagear." >&2
    exit 1
fi

if git ls-remote --tags "$REPO_REMOTE" "$TAG" 2>/dev/null | grep -q "$TAG"; then
    echo "ERROR: tag $TAG ya existe en remote ($REPO_REMOTE). Las tags son inmutables." >&2
    exit 1
fi

# ── 7. Build admin-panel SPA y empaquetar dist en el wheel ──
#
# v1.6.0: el wheel incluye el React SPA buildeado para que consumers
# que activen `admin_panel=True` en su create_app() obtengan el admin
# UI funcional sin necesidad de Node ni clonar el repo del core.
#
# Estrategia:
#   - npm install + npm run build en admin-panel/
#   - Copiar admin-panel/dist/* a copiloto_core/admin/static/dist/
#     (este path está cubierto por `[tool.setuptools.package-data]
#     "copiloto_core" = ["admin/static/dist/**/*"]` → entra al wheel).
#   - Force-add del nuevo dist y commit ANTES del tag, para que el
#     `git push HEAD` lleve los assets como parte del release commit.
#
# Skipeable con --skip-admin-build (útil para hotfixes que no tocan UI):
SKIP_ADMIN_BUILD=0
if [[ "${SKIP_ADMIN_BUILD_OPT:-}" == "1" ]]; then
    SKIP_ADMIN_BUILD=1
fi

if [[ $SKIP_ADMIN_BUILD -eq 0 ]]; then
    if ! command -v npm >/dev/null 2>&1; then
        echo "ERROR: npm no encontrado en PATH (necesario para build admin SPA)." >&2
        echo "Instalá Node ≥18 o pasá SKIP_ADMIN_BUILD_OPT=1 si no querés rebuildear." >&2
        exit 1
    fi
    echo "▶ Buildeando admin SPA con npm..."
    (
        cd admin-panel
        if [[ ! -d node_modules ]]; then
            echo "  (npm install — primera vez)"
            npm install --silent
        fi
        rm -rf dist
        npm run build
    )

    echo "▶ Copiando dist a copiloto_core/admin/static/dist/ (package-data)"
    rm -rf copiloto_core/admin/static/dist
    mkdir -p copiloto_core/admin/static/dist
    cp -r admin-panel/dist/* copiloto_core/admin/static/dist/

    if ! git diff --quiet copiloto_core/admin/static/dist 2>/dev/null \
        || ! git ls-files --error-unmatch copiloto_core/admin/static/dist/index.html >/dev/null 2>&1; then
        echo "▶ Commiteando assets del SPA (parte del release commit)"
        git add copiloto_core/admin/static/dist
        git commit -m "build: refresh admin SPA dist for $TAG" || {
            echo "  (no hay cambios en dist — skip commit)"
        }
    fi
fi

# ── 8. Tag + push ──
if [[ $DRY_RUN -eq 1 ]]; then
    echo "DRY RUN — acciones que se ejecutarían:"
    echo "  git tag -a $TAG -m 'Release $TAG'"
    echo "  git push $REPO_REMOTE HEAD"
    echo "  git push $REPO_REMOTE $TAG"
    exit 0
fi

echo "▶ Creando tag $TAG..."
git tag -a "$TAG" -m "Release $TAG"

echo "▶ Pusheando branch + tag a $REPO_REMOTE..."
git push "$REPO_REMOTE" HEAD
git push "$REPO_REMOTE" "$TAG"

echo ""
echo "✅ Release $TAG publicado."
echo ""
echo "Los módulos consumidores pueden ahora pinear:"
echo "  copiloto-core @ git+ssh://git@github.com/agentecopilotoai-code/copiloto-core.git@$TAG"
