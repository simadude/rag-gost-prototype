"""Нода distribute_tasks: разбивает контекст на задачи по одному пункту ГОСТа и распределяет их по агентам проверки..

Источник в декомпозиции: C1 Оркестратор. Контракт — docs/module-standard.md.
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port


class DistributeTasks(BaseModule):
    """Разбивает контекст на задачи по одному пункту ГОСТа и распределяет их по агентам проверки."""

    name = "distribute_tasks"
    description = "Разбивает контекст на задачи по одному пункту ГОСТа и распределяет их по агентам проверки"
    total_steps = 2

    def execute(self, data: DataObject) -> DataObject:
        """Одна задача = одна пара «пункт ГОСТ + фрагмент решения».

        Приоритет входа: собранные пары `context_pairs`; если пар нет (минимальный
        прогон) — каждая кандидатура из векторного канала становится задачей.
        На холостом прогоне кандидатов нет — объект данных не меняется.
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, "шаг {} из {}: разбиение контекста на задачи".format(step, self.total_steps))
            self.pace()
        pairs = data.context_pairs or [
            (candidate, None) for candidate in data.candidate_requirements
        ]
        if pairs:
            data.tasks = [
                {
                    "id": f"task-{i:03d}",
                    "requirement": requirement,
                    "fragment": fragment,
                }
                for i, (requirement, fragment) in enumerate(pairs, start=1)
            ]
            validate_port("tasks", data.tasks)
        return data
