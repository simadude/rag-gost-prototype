"""Нода rerank_fragments: пересортировывает и фильтрует найденные пункты ГОСТа, снимая дубли перед сборкой контекста..

Источник в декомпозиции: B3 Ретривер (реранкинг). Контракт — docs/module-standard.md.
B2: реранк — модельная пересортировка (не эвристика): коннектор
`providers.reranker.get_reranker()` — служба за внешним контуром; запрос —
текст чанка решения, документы — кандидаты трёх каналов.
"""
from __future__ import annotations

import json
import os

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port
from providers.reranker import get_reranker


def _key(hit: dict) -> str:
    """Ключ дедупликации: id чанка корпуса, если есть, иначе сам текст."""
    return str(hit.get("id") or json.dumps(hit, ensure_ascii=False)) if isinstance(hit, dict) else str(hit)


def _text(hit: dict) -> str:
    return str(hit.get("text", "")) if isinstance(hit, dict) else str(hit)


class RerankFragments(BaseModule):
    """Пересортировывает и фильтрует найденные пункты ГОСТа, снимая дубли перед сборкой контекста."""

    name = "rerank_fragments"
    description = "Пересортировывает и фильтрует найденные пункты ГОСТа, снимая дубли перед сборкой контекста"
    total_steps = 3

    def execute(self, data: DataObject) -> DataObject:
        """Слияние трёх каналов → дедупликация → реранк по каждому чанку решения.

        Модельный реранк требует привязки «кандидат → чанк решения» (её ставит
        retrieve_fragments); кандидаты без привязки идут в хвост. На холостом
        прогоне кандидатов нет — объект данных не меняется.
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, "шаг {} из {}: слияние каналов и реранк".format(step, self.total_steps))
            self.pace()
        merged: list[dict] = []
        seen: set[str] = set()
        for hit in [*data.candidate_requirements, *data.literal_hits, *data.graph_candidates]:
            if not isinstance(hit, dict):
                continue
            key = _key(hit)
            if key in seen:
                continue
            seen.add(key)
            merged.append(hit)
        if not merged:
            return data

        reranker = get_reranker()
        limits = reranker.limits()
        top_k = int(os.environ.get("RAG_RERANK_TOP_K", "3"))
        solution_by_id = {str(chunk.get("id", "")): chunk for chunk in data.chunks}

        # Реранк внутри каждого чанка решения: один вызов реранкера на группу,
        # из группы выживают top-K лучших пар «пункт ↔ этот фрагмент» — так у
        # каждого фрагмента решения остаются свои пункты для проверки.
        groups: dict[str, list[int]] = {}
        for order, hit in enumerate(merged):
            groups.setdefault(str(hit.get("solution_chunk_id", "")), []).append(order)
        selected: list[int] = []
        for chunk_id, orders in groups.items():
            chunk = solution_by_id.get(chunk_id)
            if chunk is None:
                continue  # кандидаты без привязки к чанку решения не проверяются
            docs = [_text(merged[order]) for order in orders]
            group_scores = reranker.rerank(_text(chunk), docs)
            ranked = sorted(zip(group_scores, orders), key=lambda pair: -pair[0])
            selected.extend(order for _, order in ranked[:top_k])
        # Порядок отбора: внутри группы по score, группы — по чанкам решения.
        selected.sort()
        data.selected_requirements = [merged[order] for order in selected]
        validate_port("selected_requirements", data.selected_requirements)
        print(
            f"rerank_fragments: реранк {limits.model}: {len(merged)} кандидатов "
            f"в {len(groups)} группах → top-{top_k} на группу = {len(data.selected_requirements)} пар"
        )
        return data
