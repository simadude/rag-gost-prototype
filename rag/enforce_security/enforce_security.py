"""Нода enforce_security: проверяет права доступа и локальность данных: корпоративные СТО не покидают контур компании..

Источник в декомпозиции: E3 Безопасность. Контракт — docs/module-standard.md.
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject


class EnforceSecurity(BaseModule):
    """Проверяет права доступа и локальность данных: корпоративные СТО не покидают контур компании."""

    name = "enforce_security"
    description = "Проверяет права доступа и локальность данных: корпоративные СТО не покидают контур компании"
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
