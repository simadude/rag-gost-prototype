"""Нода literal_search: дословный поиск: находит точные совпадения текста и чисел по корпусу ГОСТа.

Источник в декомпозиции: Слой поиска: дословный поиск по числам. Контракт — docs/module-standard.md.
A4 (лекция 11:10–13:10): чтение из БД — ходка к провайдеру за ответом, не сквозной
поток; коннектор `providers.stores.get_vector_store().search_literal()` — точные
совпадения по текстам чанков корпуса (векторный поиск плохо работает на числах,
поэтому канал дословного поиска отдельный).
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port
from core.targets import hit_in_targets
from providers.stores import get_vector_store


class LiteralSearch(BaseModule):
    """Дословный поиск: находит точные совпадения текста и чисел по корпусу ГОСТа."""

    name = "literal_search"
    description = "Дословный поиск: находит точные совпадения текста и чисел по корпусу ГОСТа."
    total_steps = 2

    def execute(self, data: DataObject) -> DataObject:
        """Дословный канал: ходка к провайдеру SQL-БД за точными совпадениями.

        На холостом прогоне чанков решения нет — объект данных не меняется.
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, "заглушка: шаг {} из {}".format(step, self.total_steps))
            self.pace()
        if data.chunks:
            store = get_vector_store()
            targets = (data.request.target_gosts if data.request else []) or []
            query_text = str(data.chunks[0].get("text", ""))[:64]
            hits = store.search_literal(query_text, top_k=20)
            data.literal_hits = [hit for hit in hits if hit_in_targets(hit, targets)]
            validate_port("literal_hits", data.literal_hits)
        return data
