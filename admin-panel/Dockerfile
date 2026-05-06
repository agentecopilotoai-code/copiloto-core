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

COPY app ./app
COPY --from=web-build /web/dist ./app/admin/static/dist

CMD ["python3", "-m", "uvicorn", "app.admin.main:app", "--host", "0.0.0.0", "--port", "3000"]
