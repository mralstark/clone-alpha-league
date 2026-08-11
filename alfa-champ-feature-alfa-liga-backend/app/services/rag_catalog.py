import logging
from typing import Any, List

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeBaseEntry

logger = logging.getLogger("alfa_liga.rag_catalog")

# Try sentence-transformers; fall back to deterministic random vector for environments without it
try:
    from sentence_transformers import SentenceTransformer
    _embedder = SentenceTransformer("all-MiniLM-L6-v2")
except Exception:
    _embedder = None


class RAGCatalogService:
    """Сервис векторного поиска B2B-кейсов.

    Для рабочей Postgres/pgvector-установки можно адаптировать embedding-столбец
    на тип Vector(384) и включить SQL-ровный K-NN. Для тестов используется Python K-NN.
    """

    def __init__(self, embedding_dim: int = 384):
        self.embedding_dim = embedding_dim

    def encode_text(self, text: str) -> List[float]:
        if _embedder is not None:
            vec = _embedder.encode(text, convert_to_numpy=True)
            # ensure float32 -> python floats
            vec = np.asarray(vec, dtype=float)
            # normalize
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            return vec.tolist()

        # deterministic fallback
        rng = np.random.RandomState(abs(hash(text)) % (2 ** 32))
        v = rng.randn(self.embedding_dim).astype(float)
        v /= np.linalg.norm(v) if np.linalg.norm(v) > 0 else 1.0
        return v.tolist()

    def build_context_query(
        self,
        category: str,
        okved: str | None,
        target_metric: str,
        metric_drop_pct: float,
        season: str | None = None,
    ) -> str:
        return (
            f"Категория бизнеса: {category}. ОКВЭД: {okved or 'Общий'}. "
            f"Просадка метрики {target_metric} на {metric_drop_pct:.1f}%. "
            f"Сезонность: {season or 'Всесезонный'}. Требуется спринт роста."
        )

    def _cosine_sim(self, a: List[float], b: List[float]) -> float:
        a = np.asarray(a, dtype=float)
        b = np.asarray(b, dtype=float)
        if a.size == 0 or b.size == 0:
            return -1.0
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na == 0 or nb == 0:
            return -1.0
        return float(np.dot(a, b) / (na * nb))

    def search_similar_sprints(
        self,
        session: Session,
        category: str,
        target_metric: str,
        metric_drop_pct: float = 0.0,
        okved: str | None = None,
        season: str | None = None,
        top_k: int = 3,
    ) -> List[dict[str, Any]]:
        query_text = self.build_context_query(category, okved, target_metric, metric_drop_pct, season)
        qvec = self.encode_text(query_text)

        # fetch candidates filtered by category + metric for efficiency
        stmt = select(KnowledgeBaseEntry).where(
            KnowledgeBaseEntry.category == category,
            KnowledgeBaseEntry.target_metric == target_metric,
        )
        rows = session.execute(stmt).scalars().all()

        if not rows:
            # fallback to full table scan
            stmt2 = select(KnowledgeBaseEntry)
            rows = session.execute(stmt2).scalars().all()

        scored = []
        for entry in rows:
            try:
                emb = entry.embedding or []
                score = self._cosine_sim(qvec, emb)
                scored.append((score, entry))
            except Exception:
                continue

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [entry for _, entry in scored[:top_k]]

        results = []
        for e in top:
            results.append(
                {
                    "sprint_id": e.id,
                    "title": e.title,
                    "description": e.description,
                    "target_metric": e.target_metric,
                    "action_items": e.action_items,
                    "associated_products": e.associated_products,
                    "source": "rag_kb_knn",
                }
            )

        logger.info(f"RAG K-NN returned {len(results)} items for {category}/{target_metric}")
        return results
