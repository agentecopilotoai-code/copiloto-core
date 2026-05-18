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
# BUG-050: `list_runbooks()` y los detail endpoints leen MD desde
# `docs/runbooks/` en runtime. Sin esta copia, los endpoints devuelven 404
# en producción aunque las rutas están registradas.
COPY docs/runbooks ./docs/runbooks

CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
