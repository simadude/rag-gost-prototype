"""Нода parse_document: извлекает текст, таблицы и схемы из документа с привязкой к страницам.

Источник в декомпозиции: A2 Парсер. Контракт — docs/module-standard.md.
Реальный минимум (TASKS-3/B1): разбор через коннектор `providers.parsers`
(PDF — poppler pdftotext за внешним контуром; DOCX — stdlib, таблицы
сохраняются строками «a | b | c»; TXT/MD — целиком). Структура не
выбрасывается: страницы, абзацы, таблицы; страница фиксирована в каждом фрагменте.
Форматы: pdf / docx / txt / md.
"""
from __future__ import annotations

from pathlib import Path

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port
from providers.parsers import parse_document_file


class ParseDocument(BaseModule):
    """Извлекает текст, таблицы и схемы из PDF с привязкой к страницам (общий для корпуса и решения)."""

    name = "parse_document"
    description = "Извлекает текст, таблицы и схемы из документов корпуса и решения с привязкой к страницам"
    total_steps = 2

    def execute(self, data: DataObject) -> DataObject:
        """Разбирает каждый файл из `source_files` в `documents` (страницы + текст).

        На холостом прогоне файлов нет — объект данных не меняется
        (TASKS.md Задача 4). Ошибка разбора одного файла не валит прогон:
        уходит в `data.errors`, остальные продолжают разбираться.
        """
        self.observe(1, "разбор файлов коннектором")
        self.pace()
        for number, source in enumerate(data.source_files, start=1):
            path = Path(source)
            try:
                parsed = parse_document_file(path)
            except Exception as exc:  # noqa: BLE001 - сбой файла не валит индексацию
                data.errors.append(f"{self.name}: {path.name}: {type(exc).__name__}: {exc}")
                continue
            data.documents.append({
                "id": f"doc-{number:04d}",
                "source": str(path),
                "name": path.name,
                "kind": parsed["kind"],
                "pages": parsed["pages"],
            })
        self.observe(2, f"разобрано документов: {len(data.documents)}")
        self.pace()
        validate_port("documents", data.documents)
        return data
