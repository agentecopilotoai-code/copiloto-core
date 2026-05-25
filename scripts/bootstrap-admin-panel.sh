#!/usr/bin/env bash
set -euo pipefail

# Compila el Admin Panel React, construye la imagen Docker y levanta el
# servicio admin-panel.
#
# Uso:
#   ./scripts/bootstrap-admin-panel.sh
#       npm install + build + docker build + docker compose up -d --force-recreate admin-panel
#
#   ./scripts/bootstrap-admin-panel.sh --build-only
#       construye imagen Docker pero no levanta contenedor
#
#   ./scripts/bootstrap-admin-panel.sh --skip-docker
#       solo build local del frontend (sin Docker)
#
#   ./scripts/bootstrap-admin-panel.sh --no-cache
#       fuerza rebuild de TODAS las capas Docker (sin reusar cache).
#       Usar cuando: cambios en admin-panel/src/ no aparecen en el bundle
#       tras un rebuild normal, o cuando se cambia el Dockerfile.
#
#   Combinables: ej. `--no-cache --build-only`
#
# Por qué `--force-recreate` por default: sin esto, docker-compose puede
# dejar corriendo el container viejo aunque la imagen haya cambiado, y
# los assets servidos (el bundle JS) siguen siendo los del build previo.

START_SERVICE=true
SKIP_DOCKER=false
NO_CACHE=false

for arg in "$@"; do
  case "$arg" in
    --up)
      # Compatibilidad con versiones anteriores: ahora levantar el servicio es el comportamiento default.
      START_SERVICE=true
      ;;
    --build-only)
      START_SERVICE=false
      ;;
    --skip-docker)
      SKIP_DOCKER=true
      START_SERVICE=false
      ;;
    --no-cache)
      NO_CACHE=true
      ;;
    *)
      echo "Argumento no soportado: $arg" >&2
      echo "Uso: $0 [--build-only|--skip-docker] [--no-cache]" >&2
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

# Hash del bundle ANTES del build — sirve para detectar si Docker reutilizó
# cache sin re-buildear el frontend (caso común: cambias .js pero olvidas
# tocar package.json, y BuildKit reusa la capa `RUN npm run build`).
hash_bundle_in_container() {
  docker compose exec -T admin-panel sh -c \
    'ls /app/app/admin/static/dist/assets/index-*.js 2>/dev/null | head -1' \
    2>/dev/null || true
}
PREV_BUNDLE_HASH="$(hash_bundle_in_container)"

echo "▶ Instalando dependencias React"
if [ -f admin-panel/package-lock.json ]; then
  npm --prefix admin-panel ci
else
  npm --prefix admin-panel install
fi

echo "▶ Compilando Admin Panel React (build local — sanity check)"
npm --prefix admin-panel run build

if [ "$SKIP_DOCKER" = "true" ]; then
  echo "✅ Build local completado; se omitió Docker por --skip-docker."
  exit 0
fi

need_cmd docker

if [ "$NO_CACHE" = "true" ]; then
  echo "▶ Construyendo imagen Docker admin-panel (--no-cache: rebuild completo)"
  docker compose build --no-cache admin-panel
else
  echo "▶ Construyendo imagen Docker admin-panel"
  docker compose build admin-panel
fi

if [ "$START_SERVICE" = "true" ]; then
  echo "▶ Levantando servicio admin-panel (--force-recreate)"
  # `--force-recreate` garantiza que docker-compose descarta el container
  # viejo y crea uno nuevo con la imagen recién construida. Sin esto, si
  # el container existente está "healthy", compose lo deja corriendo
  # aunque la imagen haya cambiado y los assets servidos serían los del
  # build previo.
  docker compose up -d --force-recreate admin-panel
  echo "▶ Estado del servicio admin-panel"
  docker compose ps admin-panel

  # Esperar a que el container reporte healthy antes de validar el bundle.
  echo "▶ Esperando container healthy (hasta 60s)…"
  for i in $(seq 1 30); do
    STATUS="$(docker compose ps admin-panel --format json 2>/dev/null | \
              grep -o '"Health":"[^"]*"' | head -1 | cut -d'"' -f4 || echo '')"
    if [ "$STATUS" = "healthy" ]; then
      break
    fi
    sleep 2
  done

  # Verificación: el bundle JS dentro del container debería tener un hash
  # NUEVO (Vite hashea el bundle por contenido). Si el hash es idéntico
  # al de antes, Docker reusó cache y el rebuild fue inefectivo.
  NEW_BUNDLE_HASH="$(hash_bundle_in_container)"
  echo ""
  echo "Bundle previo : ${PREV_BUNDLE_HASH:-<ninguno>}"
  echo "Bundle nuevo  : ${NEW_BUNDLE_HASH:-<ninguno>}"

  if [ -n "$PREV_BUNDLE_HASH" ] && [ "$PREV_BUNDLE_HASH" = "$NEW_BUNDLE_HASH" ] && [ "$NO_CACHE" != "true" ]; then
    cat <<'WARN'

⚠ El hash del bundle JS NO cambió. Posibles causas:
  - No hubo cambios reales en admin-panel/src/ desde el último build.
  - Docker reutilizó la capa cacheada `RUN npm run build`.

Si hiciste cambios en admin-panel/src/ que esperabas ver, re-corré con:
  ./scripts/bootstrap-admin-panel.sh --no-cache

Eso fuerza a Docker a invalidar TODAS las capas y rebuildear desde cero.
WARN
  fi
fi

cat <<'SUMMARY'

✅ Admin Panel listo
URLs:
  Platform admin:          http://localhost:3000/admin
  Gestión Documental:      http://localhost:3000/gd/t/<slug>
  GD admin del módulo:     http://localhost:3000/gd/admin/t/<slug>
  Influencer:              http://localhost:3000/t/<slug>/influencer  (legacy)
  Chatbot:                 http://localhost:3000/t/<slug>             (legacy)
  Entry SPA (autoredir):   http://localhost:3000/

Recordá hacer hard refresh del navegador (Cmd+Shift+R o
DevTools → click derecho en recargar → "Empty Cache and Hard Reload")
para que el browser descargue el bundle nuevo.

Si no abre o ves algo raro, revisá:
  docker compose ps admin-panel
  docker compose logs -f admin-panel
SUMMARY
