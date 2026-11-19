# The backend image: Python, the pinned dependencies of backend/pyproject.toml (the test group too,
# because the tests run in this image) and the code. docker-compose.yml also mounts ./backend at
# /app, so code changes apply without a rebuild; a changed dependency needs ./scripts/setup.sh.
FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir --group test
COPY . .

# Migrate first, then serve. One uvicorn process; --reload restarts it on code changes.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --reload"]
