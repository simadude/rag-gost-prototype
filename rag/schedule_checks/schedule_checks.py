"""Нода schedule_checks: ставит задание на проверку в очередь и распределяет лимиты и стоимость обращений к LLM API..

Источник в декомпозиции: E1 Backend/API. Контракт — docs/module-standard.md.
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject


class ScheduleChecks(BaseModule):
    """Ставит задание на проверку в очередь и распределяет лимиты и стоимость обращений к LLM API."""

    name = "schedule_checks"
    description = "Ставит задание на проверку в очередь и распределяет лимиты и стоимость обращений к LLM API"
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
