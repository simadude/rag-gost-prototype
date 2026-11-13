"""Нода graph_search: графовый поиск: находит связанные факты и пункты ГОСТа через связи в базе знаний.

Источник в декомпозиции: Слой графового поиска. Контракт — docs/module-standard.md.
A4 (лекция 11:10–13:10): чтение из базы знаний — ходка к провайдеру за ответом
(свой коннектор `providers.stores.get_knowledge_base()`); факты и связи кладёт
индексация (store_facts), поиск их достаёт — сквозного потока через базу нет.
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port
from core.targets import doc_prefixes, fact_in_docs
from providers.stores import get_knowledge_base


class GraphSearch(BaseModule):
    """Графовый поиск: находит связанные факты и пункты ГОСТа через связи в базе знаний."""

    name = "graph_search"
    description = "Графовый поиск: находит связанные факты и пункты ГОСТа через связи в базе знаний."
    total_steps = 2

    def execute(self, data: DataObject) -> DataObject:
        """Графовый канал: ходка к провайдеру базы знаний за связанными фактами.

        На холостом прогоне кандидатов нет — объект данных не меняется.
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, "заглушка: шаг {} из {}".format(step, self.total_steps))
            self.pace()
        if data.candidate_requirements:
            kb = get_knowledge_base()
            targets = (data.request.target_gosts if data.request else []) or []
            ids = [str(candidate.get("id", "")) for candidate in data.candidate_requirements]
            facts = kb.linked_facts(ids)
            if targets:
                # Факты ограничиваем документами из целевых нормативов:
                # префиксы doc-XXXX берём у кандидатов, прошедших фильтр.
                prefixes = doc_prefixes(data.candidate_requirements, targets)
                facts = [fact for fact in facts if fact_in_docs(fact, prefixes)]
            data.graph_candidates = facts
            validate_port("graph_candidates", data.graph_candidates)
        return data
