FROM node:22-alpine AS web-build

WORKDIR /web
COPY admin-panel/package*.json ./
RUN npm install
COPY admin-panel ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install .

COPY copiloto_core ./copiloto_core
COPY --from=web-build /web/dist ./copiloto_core/admin/static/dist

# SEC-020-N (audit#4) — non-root user. Crear ANTES de cambiar owner
# para que el COPY anterior se haga como root (default) y luego
# transferir ownership. El binding al puerto 3000 NO requiere
# privilegios (>1024), por lo que running as `copiloto` (uid 10001)
# es seguro.
RUN groupadd --system --gid 10001 copiloto \
    && useradd --system --uid 10001 --gid copiloto --no-create-home copiloto \
    && chown -R copiloto:copiloto /app
USER copiloto

CMD ["python3", "-m", "uvicorn", "copiloto_core.admin.main:app", "--host", "0.0.0.0", "--port", "3000"]
