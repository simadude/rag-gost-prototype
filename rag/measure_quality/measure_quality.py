"""Нода measure_quality: считает метрики качества проверки: полнота покрытия пунктов, доля подтверждённых вердиктов..

Источник в декомпозиции: E4 Метрики качества. Контракт — docs/module-standard.md.
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject


class MeasureQuality(BaseModule):
    """Считает метрики качества проверки: полнота покрытия пунктов, доля подтверждённых вердиктов."""

    name = "measure_quality"
    description = "Считает метрики качества проверки: полнота покрытия пунктов, доля подтверждённых вердиктов"
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
