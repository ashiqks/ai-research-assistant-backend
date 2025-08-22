from typing import Any, Dict, List

from app.memory.embeddings import embed_texts
from app.memory.vector_store import FaissStore
from app.db.session import SessionLocal
from app.db.models import Memory

_vector: FaissStore | None = None


def _get_store() -> FaissStore:
    global _vector
    if _vector is None:
        # Embedding dimension for all-MiniLM-L6-v2
        _vector = FaissStore(dim=384)
    return _vector


def store_memory(user_id: int, content: str, metadata: Dict[str, Any] | None = None) -> int:
    db = SessionLocal()
    try:
        memory = Memory(user_id=user_id, content=content, meta=metadata or {})
        db.add(memory)
        db.commit()
        db.refresh(memory)

        vec = embed_texts([content])[0]
        _get_store().add([vec], [{"memory_id": memory.id, "user_id": user_id, **(metadata or {})}])
        return memory.id
    finally:
        db.close()


def retrieve_memory(user_id: int, query: str, k: int = 5) -> List[Dict[str, Any]]:
    vec = embed_texts([query])[0]
    hits = _get_store().search(vec, k=k)
    filtered = [h for h in hits if h.get("metadata", {}).get("user_id") == user_id]
    return filtered or hits
