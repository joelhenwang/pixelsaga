# Production API image (owned by S5-HARD-001).
#
# Build from the repo root so `backend/` and `content/` stay aligned:
#   docker build -f backend/Dockerfile -t worldsim-api .
# Run with the database URL, seed content, and (for non-loopback binds)
# the public-bind key; see compose.yaml and .env.example.
# The entrypoint runs from /app so relative content paths resolve
# exactly like a repo-root checkout.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
ENV PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./backend/
COPY backend/src ./backend/src
RUN pip install --no-cache-dir uv \
    && uv sync --project backend --frozen --no-dev
COPY backend/migrations ./backend/migrations
COPY backend/prompts ./backend/prompts
COPY backend/alembic.ini ./backend/alembic.ini
COPY content ./content

EXPOSE 8000
ENTRYPOINT ["sh", "-c", "uv run --project backend --no-dev alembic -c backend/alembic.ini upgrade head && exec uv run --project backend --no-dev python -m worldsim.interfaces.cli serve"]
