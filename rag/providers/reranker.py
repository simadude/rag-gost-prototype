"""Реранкер-служба за внешним контуром (B2/B3: пересортировка кандидатов).

Служба llama.cpp: `llama-server --reranking` с Qwen3-Reranker; endpoint
`/v1/rerank` (Jina-формат). Официальный рецепт сборки GGUF — conversion/qwen.py
в поставке llama.cpp: нужен тензор cls.output.weight (строки yes/no связанного
эмбеддинга), qwen3.classifier.output_labels и rerank-шаблон в метаданных —
у «голого» конверта скоринги вырождаются (у нас было 1e-28).

Ключ замечен в проекте в одном месте: смена модели/службы — переменные
окружения, ноды не трогаются.
"""
from __future__ import annotations

import json
import os
import urllib.request


class RerankerLimits:
    """Входные ворота реранкера (B1): длина документа и запроса."""

    def __init__(self, max_query_chars: int, max_doc_chars: int, model: str) -> None:
        self.max_query_chars = max_query_chars
        self.max_doc_chars = max_doc_chars
        self.model = model


class Reranker:
    """Интерфейс коннектора к реранкер-службе."""

    def limits(self) -> RerankerLimits:  # noqa: D401
        raise NotImplementedError

    def rerank(self, query: str, documents: list[str]) -> list[float]:  # noqa: D401
        """Возвращает score по каждому документу в исходном порядке."""
        raise NotImplementedError


class StubReranker(Reranker):
    """Заглушка: порядок на входе = порядок на выходе (scores убывающие)."""

    def limits(self) -> RerankerLimits:
        return RerankerLimits(4096, 4096, "stub")

    def rerank(self, query, documents) -> list[float]:
        return [float(len(documents) - i) for i in range(len(documents))]


class LlamaCppReranker(Reranker):
    """Коннектор к /v1/rerank службы llama.cpp (RAG_RERANKER_URL)."""

    def __init__(self, url: str | None = None) -> None:
        self._url = url or os.environ.get("RAG_RERANKER_URL", "http://127.0.0.1:8915")
        self._model = os.environ.get("RAG_RERANKER_MODEL", "qwen3-reranker-4b")
        self._limits = RerankerLimits(
            max_query_chars=int(os.environ.get("RAG_RERANKER_QUERY_CHARS", "2000")),
            max_doc_chars=int(os.environ.get("RAG_RERANKER_DOC_CHARS", "4000")),
            model=self._model,
        )

    def limits(self) -> RerankerLimits:
        return self._limits

    def rerank(self, query, documents) -> list[float]:
        if not documents:
            return []
        scores: list[float] = []
        # Батчами по 16 документов: пул пар query+doc под окно службы.
        for start in range(0, len(documents), 16):
            batch = documents[start : start + 16]
            payload = json.dumps(
                {
                    "model": self._model,
                    "query": query[: self._limits.max_query_chars],
                    "documents": [doc[: self._limits.max_doc_chars] for doc in batch],
                }
            ).encode("utf-8")
            request = urllib.request.Request(
                f"{self._url}/v1/rerank",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.loads(response.read().decode("utf-8"))
            batch_scores = [0.0] * len(batch)
            for item in body.get("results", []):
                index = int(item.get("index", -1))
                if 0 <= index < len(batch):
                    batch_scores[index] = float(item.get("relevance_score", 0.0))
            scores.extend(batch_scores)
        return scores


def get_reranker() -> Reranker:
    """Фабрика коннектора: RAG_RERANKER=stub|llamacpp."""
    backend = os.environ.get("RAG_RERANKER", "stub").lower()
    if backend == "stub":
        return StubReranker()
    if backend == "llamacpp":
        return LlamaCppReranker()
    raise ValueError(f"Неизвестный реранкер: {backend!r}")
