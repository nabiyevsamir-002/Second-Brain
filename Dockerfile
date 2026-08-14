FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Azure Speech SDK üçün native runtime kitabxanaları (az-AZ TTS).
# TTS çıxışı üçün GStreamer LAZIM DEYİL (o, yalnız sıxılmış STT girişi üçündür).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libasound2 \
        libssl3 \
    && rm -rf /var/lib/apt/lists/*

# 1) Yalnız asılılıqları quraşdır — bu layer YALNIZ pyproject.toml dəyişəndə yenilənir (keş).
#    [project.dependencies] app koduna bağlı deyil, ona görə app/ hələ kopyalanmır.
#    Beləliklə kod dəyişikliyi ağır asılılıq quraşdırmasını yenidən işə salmır (sürətli deploy).
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# 2) Tətbiq kodu + config — burada dəyişiklik yuxarıdakı asılılıq layer-ini POZMUR.
#    Tətbiq /app-dan mənbə kimi işləyir (`python -m app.main`), pip paketi (boş) shadow etmir.
COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["python", "-m", "app.main"]
