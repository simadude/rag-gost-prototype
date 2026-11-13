"""Нода collect_sources: собирает файлы корпуса (ГОСТы РФ и СТО компании) для индексации.

Источник в декомпозиции: A1 Корпус документов. Контракт — docs/module-standard.md.
Реальный минимум (TASKS-3/B1): источники задаются в `data.source_files` — файл
или папка; папка обходится рекурсивно, берутся поддерживаемые коннектором
разбора форматы (pdf/docx/txt/md), сортировка и дедупликация — переиндексация
должна быть идемпотентной.
"""
from __future__ import annotations

from pathlib import Path

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port
from providers.parsers import SUPPORTED_SUFFIXES


class CollectSources(BaseModule):
    """Собирает файлы корпуса (ГОСТы РФ и СТО компании) из папки источников для индексации."""

    name = "collect_sources"
    description = "Собирает файлы корпуса (ГОСТы РФ и СТО компании) из папки источников для индексации"
    total_steps = 2

    def execute(self, data: DataObject) -> DataObject:
        """Разворачивает файлы/папки в явный список файлов корпуса.

        На холостом прогоне источников нет — объект данных не меняется.
        """
        self.observe(1, "разворачивание источников (файл/папка)")
        self.pace()
        expanded: list[str] = []
        for source in data.source_files:
            path = Path(source)
            if path.is_dir():
                for child in sorted(path.rglob("*")):
                    if child.is_file() and child.suffix.lower() in SUPPORTED_SUFFIXES:
                        expanded.append(str(child))
            elif path.is_file():
                expanded.append(str(path))
            else:
                data.errors.append(f"{self.name}: источник не найден: {source}")
        # порядок детерминирован, дубли отброшены (идемпотентность переиндексации)
        data.source_files = sorted(dict.fromkeys(expanded))
        self.observe(2, f"файлов корпуса: {len(data.source_files)}")
        self.pace()
        validate_port("source_files", data.source_files)
        return data
