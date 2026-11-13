"""Нода format_verdict: приводит ответы агентов к схеме вердикта: статус / цитата / исправление..

Источник в декомпозиции: C2/C3. Контракт — docs/module-standard.md.
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port


class FormatVerdict(BaseModule):
    """Приводит ответы к схеме вердикта: статус / цитата / исправление."""

    name = "format_verdict"
    description = "Приводит ответы к схеме вердикта: статус / цитата / исправление"
    total_steps = 2

    def execute(self, data: DataObject) -> DataObject:
        """Нормализация сырых ответов агентов к единой схеме вердикта.

        verify_requirement уже отдаёт нормализованные записи (статус из словаря,
        проверенная цитата) — здесь формируется чистый список вердиктов без
        служебных полей (raw), пригодный для отчёта и агрегации.
        На холостом прогоне ответов нет — объект данных не меняется.
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, "шаг {} из {}: нормализация вердиктов".format(step, self.total_steps))
            self.pace()
        if data.raw_answers:
            data.verdicts = [
                {
                    "task_id": str(answer.get("task_id", "")),
                    "gost": str(answer.get("gost", "")),
                    "status": str(answer.get("status", "needs_review")),
                    "quote": str(answer.get("quote", "")),
                    "comment": str(answer.get("comment", "")),
                }
                for answer in data.raw_answers
                if isinstance(answer, dict)
            ]
            validate_port("verdicts", data.verdicts)
        return data
