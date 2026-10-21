FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# geospatial build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/repo

# repo files (repo itself stays untouched; we copy what the service needs)
COPY pyproject.toml ./
COPY services/ ./services/
COPY apps/site/ ./apps/site/
COPY data/ ./data/

RUN pip install --upgrade pip && pip install -e ".[api,ml]"

# production wrapper (serves API + dashboard on one origin)
# NOTE: docker context is the repo root (see render.yaml), so this is
# deploy/server.py relative to the context, not to the Dockerfile dir.
COPY deploy/server.py /app/server.py

ENV NUMIDIA_REPO=/app/repo \
    NUMIDIA_ACTIVE_MODEL=/app/repo/services/ml/models/verifier_v2 \
    NUMIDIA_DB_PATH=/app/repo/data/db/numidia.db

EXPOSE 8000
CMD ["sh", "-c", "uvicorn --app-dir /app server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
