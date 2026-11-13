"""Нода user_interface: принимает запрос пользователя (PDF решения и целевые ГОСТы), выбирает маршрут прогона (check/index/refresh) и показывает отчёт..

Источник в декомпозиции: B1 Интерфейс. Контракт — docs/module-standard.md.
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject


class UserInterface(BaseModule):
    """Принимает запрос пользователя (PDF решения и целевые ГОСТы), выбирает маршрут прогона (check/index/refresh) и показывает отчёт."""

    name = "user_interface"
    description = "Принимает запрос пользователя (PDF решения и целевые ГОСТы), выбирает маршрут прогона (check/index/refresh) и показывает отчёт"
    total_steps = 3

    def execute(self, data: DataObject) -> DataObject:
        """Заглушка: бизнес-логика появится в следующих проходах.

        Возвращает объект данных без изменений, чтобы граф можно было
        прогнать целиком (холостой прогон, TASKS.md Задача 4).
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, "заглушка: шаг {} из {}".format(step, self.total_steps))
            self.pace()
        return data
