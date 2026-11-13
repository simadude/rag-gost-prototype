"""Нода aggregate_verdicts: собирает вердикты, снимает конфликты, формирует сводный статус документа..

Источник в декомпозиции: C3/C4 Агрегатор. Контракт — docs/module-standard.md.
Минимальная реальность: сводный вердикт документа — худший статус по вердиктам
(violation > needs_review > compliant); конфликт — один и тот же пункт ГОСТа
с разными статусами по разным фрагментам решения (разрешение конфликта
повторной проверкой — решение о доп. расходе LM-провайдера, пока фиксируется
в отчёте как конфликт).
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port

# Порядок «худшести» статуса: чем меньше индекс, тем хуже для документа.
_SEVERITY = {"violation": 0, "needs_review": 1, "compliant": 2}


class AggregateVerdicts(BaseModule):
    """Собирает вердикты, снимает конфликты, формирует сводный статус документа."""

    name = "aggregate_verdicts"
    description = "Собирает вердикты, снимает конфликты, формирует сводный статус документа"
    total_steps = 2

    def execute(self, data: DataObject) -> DataObject:
        """Сводный вердикт: худший статус; конфликты пунктов — отдельно в отчёт.

        На холостом прогоне вердиктов нет — объект данных не меняется.
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, "шаг {} из {}: агрегация вердиктов".format(step, self.total_steps))
            self.pace()
        if data.verdicts:
            by_status: dict[str, list[dict]] = {}
            by_gost: dict[str, list[str]] = {}
            for verdict in data.verdicts:
                status = str(verdict.get("status", "needs_review"))
                by_status.setdefault(status, []).append(verdict)
                gost = str(verdict.get("gost", ""))
                if gost:
                    by_gost.setdefault(gost, []).append(status)
            worst = sorted(
                by_status, key=lambda status: _SEVERITY.get(status, 1)
            )[0]
            conflicts = {
                gost: sorted(set(statuses))
                for gost, statuses in by_gost.items()
                if len(set(statuses)) > 1
            }
            data.summary_verdict = {
                "document_status": worst,
                "counts": {status: len(items) for status, items in sorted(by_status.items())},
                "total": len(data.verdicts),
                "conflicts": conflicts,
            }
            validate_port("summary_verdict", data.summary_verdict)
        return data
