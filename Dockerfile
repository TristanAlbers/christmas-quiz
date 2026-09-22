FROM python:3.12-slim-bookworm AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

COPY requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.lock

COPY manage.py ./
COPY config ./config
COPY quiz ./quiz
COPY games ./games
COPY tests ./tests

# The build key is discarded with this layer. Runtime requires a configured key.
RUN DJANGO_SECRET_KEY=build-only-not-used-at-runtime \
    python manage.py collectstatic --noinput \
    && mkdir -p /app/var \
    && chown -R 1000:1000 /app/var

USER 1000:1000
EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py provision_accounts && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --worker-class gthread --workers 1 --threads 4 --no-control-socket --access-logfile - --error-logfile -"]

FROM app AS dev
USER root
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    RUFF_CACHE_DIR=/tmp/ruff-cache
COPY requirements-dev.lock ./
RUN python -m pip install --no-cache-dir -r requirements-dev.lock \
    && python -m playwright install --with-deps chromium
COPY pyproject.toml ./
USER 1000:1000
