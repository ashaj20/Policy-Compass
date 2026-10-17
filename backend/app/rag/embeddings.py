"""Text embeddings behind a small interface (decision A5: local model, swappable later)."""

import hashlib
import math
import re
import threading
from functools import lru_cache
from typing import Protocol

from app.models.chunk import EMBEDDING_DIM

MODEL_NAME = "BAAI/bge-small-en-v1.5"


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedEmbedder:
    """Local ONNX model via fastembed. Loaded on first use (downloaded once, ~130 MB)."""

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._load().embed(texts)]


class HashingEmbedder:
    """Deterministic, dependency-free embedder for tests: overlapping words give similar vectors."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            v = [0.0] * EMBEDDING_DIM
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                h = int(hashlib.sha256(word.encode()).hexdigest(), 16)
                v[h % EMBEDDING_DIM] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            vectors.append([x / norm for x in v])
        return vectors


@lru_cache
def get_embedder() -> Embedder:
    return FastEmbedEmbedder()
