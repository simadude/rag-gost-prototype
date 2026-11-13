"""Нода refresh_corpus: отслеживает новые редакции ГОСТов и решает, какие документы корпуса нужно переиндексировать..

Источник в декомпозиции: E2 Обновление базы. Контракт — docs/module-standard.md.
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject


class RefreshCorpus(BaseModule):
    """Отслеживает новые редакции ГОСТов и решает, какие документы корпуса нужно переиндексировать."""

    name = "refresh_corpus"
    description = "Отслеживает новые редакции ГОСТов и решает, какие документы корпуса нужно переиндексировать"
    total_steps = 2

    def execute(self, data: DataObject) -> DataObject:
        """Заглушка: бизнес-логика появится в следующих проходах.

        Возвращает объект данных без изменений, чтобы граф можно было
        прогнать целиком (холостой прогон, TASKS.md Задача 4).
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, "заглушка: шаг {} из {}".format(step, self.total_steps))
            self.pace()
        return data
