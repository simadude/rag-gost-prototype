"""Нода chunk_text: режет документы на чанки по пунктам и разделам, добавляя метаданные.

Источник в декомпозиции: A3 Чанкер. Контракт — docs/module-standard.md.
Реальный минимум (TASKS-3/B1): режет по абзацам до целевого размера (~1200
символов — рабочая длина для поиска), жёсткий потолок — входные ворота
эмбеддера (`providers.embedder.Embedder.limits().max_input_chars`): «не всякий
эмбеддер съест любой объём текста» — обратная связь эмбеддера к чанкеру.
Разметка не выбрасывается: в метаданных чанка — источник, страницы,
текущий раздел (заголовки ГОСТ/СТО: нумерованные пункты и «капс»-строки).
"""
from __future__ import annotations

import re

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port
from providers.embedder import get_embedder

TARGET_CHARS = 1200          # рабочая длина чанка для качества поиска
_HEADING_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)*[.)]?\s+\S.*| глава \d.*| приложение [а-яёa-z].*|[А-ЯЁA-Z][А-ЯЁA-Z0-9\s.,()«»–-]{5,90})$"
)


class ChunkText(BaseModule):
    """Режет документы на чанки по пунктам и разделам, добавляя метаданные (номер ГОСТа, пункт, редакция)."""

    name = "chunk_text"
    description = "Режет документы на чанки по пунктам и разделам, добавляя метаданные (номер ГОСТа, пункт, редакция)"
    total_steps = 3

    def execute(self, data: DataObject) -> DataObject:
        """Абзацы документов группируются в чанки: target ~1200 символов,
        потолок — ворота эмбеддера; метаданные: source/name/pages/section.
        На холостом прогоне документов нет — объект данных не меняется."""
        self.observe(1, "лимиты эмбеддера (входные ворота)")
        self.pace()
        if not data.documents or data.chunks:
            for step in (2, 3):
                self.observe(step, "чанкование не требуется")
                self.pace()
            return data
        limits = get_embedder().limits()
        self.observe(2, "группировка абзацев в чанки")
        self.pace()
        counter = 0
        for document in data.documents:
            chunks = self._chunk_document(document, limits.max_input_chars)
            data.chunks.extend(chunks)
            counter += len(chunks)
        self.observe(3, f"чанков: {counter} (лимит входа {limits.max_input_chars} симв.)")
        self.pace()
        validate_port("chunks", data.chunks)
        return data

    def _chunk_document(self, document: dict, max_chars: int) -> list[dict]:
        """Параграфы (с номером страницы) → чанки ≤ target, жёстко ≤ max_chars."""
        source = document.get("source", "")
        name = document.get("name", "")
        doc_id = document.get("id", "doc")
        # абзацы с привязкой к странице
        paragraphs: list[tuple[int | None, str]] = []
        for page in document.get("pages", []):
            page_number = page.get("page")
            for line in str(page.get("text", "")).split("\n"):
                stripped = line.strip()
                if stripped:
                    paragraphs.append((page_number, stripped))
        chunks: list[dict] = []
        buffer: list[str] = []
        buffer_pages: set = set()
        section = ""

        def flush() -> None:
            nonlocal buffer, buffer_pages, section, counter
            if not buffer:
                return
            counter += 1
            text = "\n".join(buffer)
            pages = sorted(p for p in buffer_pages if p is not None)
            chunks.append({
                "id": f"{doc_id}#c{counter:04d}",
                "source": source,
                "name": name,
                "pages": pages,
                "section": section,
                "text": text,
            })
            buffer, buffer_pages = [], set()

        counter = 0
        for page_number, line in paragraphs:
            if _HEADING_RE.match(line) and len(line) <= 120:
                section = line  # раздел обновляем, заголовок остаётся в тексте
            if len(line) > max_chars:
                # абзац длиннее ворот: режем посреди абзаца (страховка чанкера)
                flush()
                for i in range(0, len(line), max_chars):
                    counter += 1
                    chunks.append({
                        "id": f"{doc_id}#c{counter:04d}",
                        "source": source, "name": name,
                        "pages": [page_number] if page_number is not None else [],
                        "section": section,
                        "text": line[i:i + max_chars],
                    })
                continue
            if buffer and sum(len(x) for x in buffer) + len(line) + 1 > TARGET_CHARS:
                flush()
            buffer.append(line)
            if page_number is not None:
                buffer_pages.add(page_number)
            if sum(len(x) for x in buffer) + len(line) > max_chars:  # pragma: no cover - защита
                flush()
        flush()
        return chunks
