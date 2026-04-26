# ── Build stage ────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="shieldai"
LABEL description="ShieldAI — AI Security Firewall"

# Non-root user
RUN addgroup --system shieldai && adduser --system --ingroup shieldai shieldai

WORKDIR /app

# Copy installed packages
COPY --from=builder /install /usr/local

# Copy application source
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Drop privileges
USER shieldai

# Render sets PORT dynamically — we expose 8000 as default but CMD reads $PORT
EXPOSE 8000

# Health check — Render uses this
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8000}/health')"

# Render injects PORT env var at runtime.
# gunicorn is more stable than uvicorn alone for production.
# -k uvicorn.workers.UvicornWorker gives us async support.
CMD gunicorn app.main:app \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --worker-class uvicorn.workers.UvicornWorker \
    --timeout 120 \
    --keep-alive 5 \
    --log-level info \
    --access-logfile -
