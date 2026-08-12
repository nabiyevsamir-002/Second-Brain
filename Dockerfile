FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# pyproject + app source, sonra quraşdır.
COPY pyproject.toml alembic.ini ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

# Migration-lar + entrypoint (app-dan sonra, ki pip layer keşdə qalsın).
COPY migrations ./migrations
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["python", "-m", "app.main"]
