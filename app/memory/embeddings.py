import os
from functools import lru_cache
from typing import List, Optional

from sentence_transformers import SentenceTransformer


DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


@lru_cache(maxsize=1)
def get_model(name: Optional[str] = None) -> SentenceTransformer:
    model_name = name or DEFAULT_MODEL
    return SentenceTransformer(model_name)


def embed_texts(texts: List[str], model_name: Optional[str] = None) -> List[List[float]]:
    model = get_model(model_name)
    vectors = model.encode(texts, normalize_embeddings=True)
    return vectors.tolist()
