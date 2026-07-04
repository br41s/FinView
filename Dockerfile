FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Deps are pinned+hashed in requirements.txt (exported from uv.lock — after any
# pyproject change run: uv lock && uv export --frozen --no-dev --no-emit-project
# -o requirements.txt). Copied before backend/ so the dep layer caches across
# code-only deploys.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend ./backend
ENV PYTHONPATH=/app

# Cloud Run injects PORT (defaults to 8080). uvicorn binds there.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT}"]
