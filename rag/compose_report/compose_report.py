"""Нода compose_report: собирает итоговый отчёт: пункт ГОСТ / фрагмент / статус / рекомендация..

Источник в декомпозиции: D1 Отчёт. Контракт — docs/module-standard.md.
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port


class ComposeReport(BaseModule):
    """Собирает итоговый отчёт: пункт ГОСТ / фрагмент / статус / рекомендация."""

    name = "compose_report"
    description = "Собирает итоговый отчёт: пункт ГОСТ / фрагмент / статус / рекомендация"
    total_steps = 2

    def execute(self, data: DataObject) -> DataObject:
        """Структура отчёта: сводный вердикт + находки (вердикт + цитата + коммент).

        Источники: summary_verdict (агрегатор) и verdicts (format_verdict).
        На холостом прогоне вердиктов нет — объект данных не меняется.
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, "шаг {} из {}: сборка отчёта".format(step, self.total_steps))
            self.pace()
        if data.verdicts:
            data.report = {
                "run_id": data.run_id,
                "document_status": (data.summary_verdict or {}).get("document_status", "needs_review"),
                "counts": (data.summary_verdict or {}).get("counts", {}),
                "conflicts": (data.summary_verdict or {}).get("conflicts", {}),
                "findings": [
                    {
                        "gost": str(verdict.get("gost", "")),
                        "status": str(verdict.get("status", "needs_review")),
                        "quote": str(verdict.get("quote", "")),
                        "comment": str(verdict.get("comment", "")),
                    }
                    for verdict in data.verdicts
                ],
            }
            validate_port("report", data.report)
        return data
