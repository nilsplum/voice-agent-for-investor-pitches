# The voice test's image (compose service e2e, run only by ./scripts/test.sh --complete): the official
# Playwright image, which brings Chrome and its system libraries and whose tag must match the pinned
# playwright package in requirements.txt, plus the test's pinned packages. docker-compose.yml mounts
# ./e2e at /e2e, so the test itself is never baked in.
FROM mcr.microsoft.com/playwright/python:v1.65.2-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /e2e
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -s shows the test's progress (one line per answer) during the conversation of several minutes;
# no cache provider, so the mounted ./e2e stays clean.
CMD ["pytest", "-q", "-s", "-p", "no:cacheprovider", "test_voice_conversation.py"]
