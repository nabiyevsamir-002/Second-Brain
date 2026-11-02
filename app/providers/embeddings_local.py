"""Lokal embedding provider — fastembed (ONNX, CPU), API açarı YOX.

Model: paraphrase-multilingual-mpnet-base-v2 (768 ölçü). AZ axtarış testində 10 sorğudan
9-u top-1 (MiniLM-L12: 6/10, potion: 6/10). DB sütunu 1536 ölçüdür (OpenAI ilə eyni) →
vektor sıfırlarla 1536-ya tamamlanır: cosine oxşarlıq DƏYİŞMİR, sxem migration-u lazım
deyil. Model dəyişəndə köhnə embedding-lər yenidən hesablanır (services/reembed.py).
"""

from __future__ import annotations

import asyncio
import math
import threading
from typing import Any

from app.models import EMBEDDING_DIM
from app.providers.base import EmbeddingProvider


def pad_unit(vec: Any, dim: int = EMBEDDING_DIM) -> list[float]:
    """Vahid uzunluğa normallaşdır + sıfırlarla `dim`-ə tamamla (cosine dəyişmir)."""
    v = [float(x) for x in vec]
    if len(v) > dim:
        raise ValueError(f"embedding ölçüsü {len(v)} > DB ölçüsü {dim}")
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v] + [0.0] * (dim - len(v))


class LocalEmbeddingProvider(EmbeddingProvider):
    # mpnet: əlaqəli qeydlər ~0.53, əlaqəsizlərin medianı ~0.78 (AZ testi).
    related_max_distance = 0.55
    local = True

    def __init__(self, model_name: str, cache_dir: str | None = None) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.model_id = f"local:{model_name}"
        self.last_total_tokens = 0  # xərc yoxdur
        self._model: Any = None
        self._lock = threading.Lock()

    def warmup(self) -> None:
        """Modeli yüklə (ilk dəfə ~1GB endirir) — startup-da arxa planda çağırılır."""
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        self.warmup()
        return [pad_unit(v) for v in self._model.embed(texts)]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._embed_sync, texts)

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]
