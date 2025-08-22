import json
from pathlib import Path
from typing import Dict, List

import faiss
import numpy as np


class FaissStore:
    def __init__(self, dim: int, persist_dir: str = ".faiss"):
        self.dim = dim
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(exist_ok=True)
        self.index_path = self.persist_dir / "index.faiss"
        self.meta_path = self.persist_dir / "meta.json"
        self.index: faiss.Index = faiss.IndexFlatIP(dim)
        self.metadatas: List[Dict] = []
        self._load()

    def _load(self) -> None:
        if self.index_path.exists():
            self.index = faiss.read_index(str(self.index_path))
        if self.meta_path.exists():
            self.metadatas = json.loads(self.meta_path.read_text())

    def _persist(self) -> None:
        faiss.write_index(self.index, str(self.index_path))
        self.meta_path.write_text(json.dumps(self.metadatas))

    def add(self, vectors: List[List[float]], metadatas: List[Dict]) -> None:
        if not vectors:
            return
        arr = np.array(vectors, dtype=np.float32)
        faiss.normalize_L2(arr)
        self.index.add(arr)
        self.metadatas.extend(metadatas)
        self._persist()

    def search(self, query: List[float], k: int = 5) -> List[Dict]:
        if not self.metadatas or self.index.ntotal == 0:
            return []
        q = np.array([query], dtype=np.float32)
        faiss.normalize_L2(q)
        scores, idxs = self.index.search(q, k)
        results: List[Dict] = []
        for i, score in zip(idxs[0], scores[0]):
            if i == -1:
                continue
            meta = self.metadatas[i] if i < len(self.metadatas) else {}
            results.append({"score": float(score), "metadata": meta})
        return results
