FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# pyproject + app source, sonra quraşdır.
COPY pyproject.toml ./
COPY app ./app

RUN pip install --upgrade pip && pip install .

CMD ["python", "-m", "app.main"]
