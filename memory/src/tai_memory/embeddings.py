"""Local embeddings via fastembed.

Default model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
(384-dim, ~50 languages incl. English + Russian, no input prefix required).
"""

import hashlib
from collections.abc import Iterable
from functools import lru_cache

from fastembed import TextEmbedding

from .config import get_settings


@lru_cache(maxsize=1)
def get_embedder() -> TextEmbedding:
    s = get_settings()
    return TextEmbedding(model_name=s.embedding_model)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embed_one(text: str, *, kind: str = "passage") -> list[float]:
    return next(iter(embed_many([text], kind=kind)))


def embed_many(texts: Iterable[str], *, kind: str = "passage") -> list[list[float]]:
    """Embed a batch of texts. `kind` is currently a no-op (kept for future e5-style models)."""
    del kind  # unused for paraphrase-multilingual-MiniLM
    return [list(v) for v in get_embedder().embed(list(texts))]
