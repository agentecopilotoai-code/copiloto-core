#!/usr/bin/env bash
set -euo pipefail

# Compila el Admin Panel React y prepara la imagen Docker del servicio admin-panel.
# Uso:
#   ./scripts/bootstrap-admin-panel.sh          # npm install + build + docker compose build admin-panel
#   ./scripts/bootstrap-admin-panel.sh --up     # además levanta el servicio
#   ./scripts/bootstrap-admin-panel.sh --skip-docker  # solo build local del frontend

UP=false
SKIP_DOCKER=false

for arg in "$@"; do
  case "$arg" in
    --up) UP=true ;;
    --skip-docker) SKIP_DOCKER=true ;;
    *)
      echo "Argumento no soportado: $arg" >&2
      exit 2
      ;;
  esac
done

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Falta dependencia: $1" >&2
    exit 1
  }
}

need_cmd npm

echo "▶ Instalando dependencias React"
if [ -f admin-panel/package-lock.json ]; then
  npm --prefix admin-panel ci
else
  npm --prefix admin-panel install
fi

echo "▶ Compilando Admin Panel React"
npm --prefix admin-panel run build

if [ "$SKIP_DOCKER" = "true" ]; then
  echo "✅ Build local completado; se omitió Docker por --skip-docker."
  exit 0
fi

need_cmd docker

echo "▶ Construyendo imagen Docker admin-panel"
docker compose build admin-panel

if [ "$UP" = "true" ]; then
  echo "▶ Levantando servicio admin-panel"
  docker compose up -d admin-panel
fi

cat <<'SUMMARY'
✅ Admin Panel listo
URL: http://localhost:3000/admin/
SUMMARY
