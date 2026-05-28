# M29 — multi-stage + non-root + HEALTHCHECK.
#
# STAGE 1 (builder): instala dependencias en un venv aislado. Esto deja
# fuera del image final el pip + cache + build artifacts (apt lists,
# wheels, etc.) — reduce el tamaño del runtime image y la superficie de
# ataque (sin pip, sin compiladores).
#
# STAGE 2 (runtime): copia el venv y la app, corre como user no-root
# (`copiloto`, UID 1000). Añade HEALTHCHECK contra `/health` para que
# orquestadores (Docker Swarm, Kubernetes liveness probe wrappers,
# docker-compose `condition: service_healthy`) detecten un crash del
# proceso aun cuando el container siga corriendo.

# ──────────────────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# build-essential queda solo en el builder; el runtime no lo necesita.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Crear un venv aislado para que el runtime stage solo copie `/opt/venv`
# (sin tocar el system Python).
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install .

# ──────────────────────────────────────────────────────────────────────────
# Runtime
# ──────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

# `curl` se mantiene para que el HEALTHCHECK (abajo) funcione sin shell-out
# a Python — más rápido y sin dependencias del venv.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 copiloto \
    && useradd --system --uid 1000 --gid copiloto --home /app --shell /usr/sbin/nologin copiloto

# Trae el venv aislado del builder. No instalamos pip ni compiladores aquí.
COPY --from=builder --chown=copiloto:copiloto /opt/venv /opt/venv

COPY --chown=copiloto:copiloto copiloto_core ./copiloto_core
# BUG-050: `list_runbooks()` y los detail endpoints leen MD desde
# `docs/runbooks/` en runtime. Sin esta copia, los endpoints devuelven 404
# en producción aunque las rutas están registradas.
COPY --chown=copiloto:copiloto docs/runbooks ./docs/runbooks

USER copiloto

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail --silent --show-error http://127.0.0.1:8000/health || exit 1

CMD ["python3", "-m", "uvicorn", "copiloto_core._runserver:app", "--host", "0.0.0.0", "--port", "8000"]
