"""Нода handle_followup: обрабатывает уточнение пользователя (переспрос, переход к пункту документа) и возвращает прогон к интерфейсу..

Источник в декомпозиции: D3 Уточнения. Контракт — docs/module-standard.md.
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject


class HandleFollowup(BaseModule):
    """Обрабатывает уточнение пользователя (переспрос, переход к пункту документа) и возвращает прогон к интерфейсу."""

    name = "handle_followup"
    description = "Обрабатывает уточнение пользователя (переспрос, переход к пункту документа) и возвращает прогон к интерфейсу"
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
