"""Нода store_vectors: записывает векторы вместе с метаданными чанков в SQL-базу данных.

Источник в декомпозиции: A5 Векторная БД. Контракт — docs/module-standard.md.
A4 (лекция 11:10–13:10): база данных — не труба, в неё *ходят* за записью;
коннектор `providers.stores.get_vector_store()` — единственный способ хода
(SQLite с WAL по умолчанию, замена на PostgreSQL — сменой RAG_VECTOR_DB).
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port
from providers.stores import get_vector_store


class StoreVectors(BaseModule):
    """Записывает векторы вместе с метаданными чанков в SQL-базу данных."""

    name = "store_vectors"
    description = "Записывает векторы вместе с метаданными чанков в SQL-базу данных"
    total_steps = 2

    def execute(self, data: DataObject) -> DataObject:
        """Записывает векторы через коннектор провайдера SQL-БД.

        На холостом прогоне векторов нет — объект данных не меняется;
        на реальном прогоне `stored_count` = сколько записей легло в БД.
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, "заглушка: шаг {} из {}".format(step, self.total_steps))
            self.pace()
        if data.vectors:
            store = get_vector_store()
            data.stored_count = store.add_many(data.vectors, data.chunks)
            validate_port("stored_count", data.stored_count)
        return data
