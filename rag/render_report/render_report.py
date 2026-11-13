"""Нода render_report: готовит показ отчёта: подсветка нарушений, экспорт PDF/MD..

Источник в декомпозиции: D2 Отчёт. Контракт — docs/module-standard.md.
Минимальный формат — Markdown (`project/var/reports/report-<run_id>.md`);
PDF и подсветка в оригинале решения — следующие проходы.
"""
from __future__ import annotations

import re
from pathlib import Path

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port

_STATUS_RU = {
    "compliant": "соответствует",
    "violation": "нарушение",
    "needs_review": "требует уточнения",
}


def _cell(text, limit: int = 200) -> str:
    """Ячейка Markdown-таблицы: без переносов, с экранированными | (ограничитель столбцов)."""
    flat = re.sub(r"\s+", " ", str(text)).strip()
    return flat.replace("|", "\\|")[:limit]


def _render_markdown(report: dict) -> str:
    lines = [
        f"# Отчёт о проверке (прогон {report.get('run_id', '')})",
        "",
        f"**Сводный статус документа: {_STATUS_RU.get(str(report.get('document_status')), str(report.get('document_status')))}**",
        "",
        "| # | Пункт | Статус | Цитата из решения | Комментарий |",
        "|---|---|---|---|---|",
    ]
    for i, finding in enumerate(report.get("findings", []), start=1):
        status = str(finding.get("status", ""))
        lines.append(
            "| {i} | {gost} | {status} | {quote} | {comment} |".format(
                i=i,
                gost=_cell(finding.get("gost", ""), 60),
                status=_STATUS_RU.get(status, status),
                quote=_cell(finding.get("quote", ""), 120),
                comment=_cell(finding.get("comment", "")),
            )
        )
    conflicts = report.get("conflicts") or {}
    if conflicts:
        lines += ["", "## Конфликты вердиктов", ""]
        for gost, statuses in sorted(conflicts.items()):
            lines.append(f"- {gost}: {', '.join(statuses)}")
    return "\n".join(lines) + "\n"


class RenderReport(BaseModule):
    """Готовит показ отчёта: подсветка нарушений, экспорт PDF/MD."""

    name = "render_report"
    description = "Готовит показ отчёта: подсветка нарушений, экспорт PDF/MD"
    total_steps = 2

    def execute(self, data: DataObject) -> DataObject:
        """Markdown-отчёт в файл + путь в presentation.

        На холостом прогоне отчёта нет — объект данных не меняется.
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, "шаг {} из {}: рендер отчёта".format(step, self.total_steps))
            self.pace()
        if data.report:
            reports_dir = Path(__file__).resolve().parent.parent / "var" / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            path = reports_dir / f"report-{data.run_id or 'run'}.md"
            path.write_text(_render_markdown(data.report), encoding="utf-8")
            data.presentation = {
                "format": "markdown",
                "path": str(path),
                "document_status": data.report.get("document_status"),
                "counts": data.report.get("counts", {}),
            }
            validate_port("presentation", data.presentation)
            print(f"render_report: отчёт записан: {path}")
        return data
