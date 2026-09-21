FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project

COPY app ./app
RUN uv sync --no-dev

# Cloud Run injects $PORT and expects the container to listen on plain HTTP
# (it terminates TLS at its own edge) — no local-HTTPS dev workflow needed
# here, unlike the sibling backend, since this service has no cookie/OAuth
# auth to make that matter locally.
ENV PORT=8080
EXPOSE 8080
# --no-access-log: uvicorn's per-request access line includes the peer IP
# and the full "GET /search?q=..." path. The app logs the search text on
# its own terms (app/main.py) and we don't want the IP retained, so the
# stock access log is off.
CMD ["sh", "-c", "uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --no-access-log"]
