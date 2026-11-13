"""Нода retrieve_fragments: ищет top-K релевантных пунктов ГОСТа по векторной близости чанков решения.

Источник в декомпозиции: B3 Ретривер. Контракт — docs/module-standard.md.
A4 (лекция 11:10–13:10): чтение из БД — тоже ходка к провайдеру за ответом,
не сквозной поток: коннектор `providers.stores.get_vector_store()` даёт
векторный канал поиска; запрос кодируется тем же эмбеддером (одна модель
для базы и запросов).
"""
from __future__ import annotations

import json
import os

from core.base_module import BaseModule
from core.targets import hit_in_targets
from core.data_object import DataObject, validate_port
from providers.embedder import get_embedder
from providers.stores import get_vector_store


class RetrieveFragments(BaseModule):
    """Ищет top-K релевантных пунктов ГОСТа по векторной близости чанков решения."""

    name = "retrieve_fragments"
    description = "Ищет top-K релевантных пунктов ГОСТа по векторной близости чанков решения"
    total_steps = 2

    def execute(self, data: DataObject) -> DataObject:
        """Векторный канал: ходка к провайдеру SQL-БД за кандидатурами.

        На холостом прогоне чанков решения нет — объект данных не меняется.
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, "заглушка: шаг {} из {}".format(step, self.total_steps))
            self.pace()
        if data.chunks:
            store = get_vector_store()
            embedder = get_embedder()
            targets = (data.request.target_gosts if data.request else []) or []
            # Векторный канал по каждому чанку решения: свой top-K, слияние
            # кандидатов с лучшим рангом по каждому источнику-кандидату.
            # Глубину задаём с запасом: фильтр целевых нормативов режет после.
            top_k = int(os.environ.get("RAG_RETRIEVE_TOP_K", "10"))
            best_rank: dict[str, tuple[int, dict]] = {}
            queries = embedder.embed([str(chunk.get("text", "")) for chunk in data.chunks])
            for chunk, query_vector in zip(data.chunks, queries):
                for rank, hit in enumerate(store.search(query_vector, top_k=top_k), start=1):
                    if not hit_in_targets(hit, targets):
                        continue  # кандидат вне целевых нормативов проверки
                    key = str(hit.get("id", json.dumps(hit, ensure_ascii=False)))
                    if key not in best_rank or rank < best_rank[key][0]:
                        found = dict(hit)
                        found["solution_chunk_id"] = str(chunk.get("id", ""))
                        best_rank[key] = (rank, found)
            data.candidate_requirements = [
                hit for _, (_, hit) in sorted(best_rank.items(), key=lambda item: item[1][0])
            ]
            if targets:
                print(f"retrieve_fragments: фильтр целевых нормативов {targets}: "
                      f"{len(data.candidate_requirements)} кандидатов")
            validate_port("candidate_requirements", data.candidate_requirements)
        return data
