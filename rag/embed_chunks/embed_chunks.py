"""Нода embed_chunks: кодирует чанки в векторы единой моделью для базы и запросов.

Источник в декомпозиции: A4 Эмбеддер. Контракт — docs/module-standard.md.
A4 (лекция 13:30–21:30): эмбеддинг — тяжёлая процедура, поэтому сама модель —
**служба за внешним контуром** (Qwen3 Embedding); нода ходит к ней только через
коннектор `providers.embedder.get_embedder()` — правильный способ ходить
к эмбеддеру, а не вшивать модель в ноду.

Входные ворота (B1, TASKS-3): «не всякий эмбеддер съест любой объём текста» —
нода читает лимиты конкретной модели (`Embedder.limits()`), режет чанки под
лимит (`fit_chunks`) и пишет отчёт о разрезах в `embedder_cuts` — обратная
связь эмбеддера к чанкеру (`embed_chunks` ↔ `chunk_text`). Структура чанков
(ГОСТ/пункт, parent_id) при разрезе сохраняется — разметку не выбрасываем.
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port
from providers.embedder import fit_chunks, get_embedder


class EmbedChunks(BaseModule):
    """Кодирует чанки в векторы единой моделью для базы и запросов, нормализует эмбеддинги."""

    name = "embed_chunks"
    description = "Кодирует чанки в векторы единой моделью для базы и запросов, нормализует эмбеддинги"
    total_steps = 2

    def execute(self, data: DataObject) -> DataObject:
        """Кодирует чанки через коннектор эмбеддер-службы (с входными воротами).

        На холостом прогоне чанков нет — объект данных не меняется
        (TASKS.md Задача 4); на реальном прогоне векторы ложатся в `vectors`.
        """
        self.observe(1, "входные ворота: лимиты модели эмбеддера")
        self.pace()
        self.observe(2, "эмбеддинг чанков")
        self.pace()
        if data.chunks:
            embedder = get_embedder()
            limits = embedder.limits()
            data.chunks, data.embedder_cuts = fit_chunks(data.chunks, limits.max_input_chars)
            validate_port("embedder_cuts", data.embedder_cuts)
            data.vectors = embedder.embed([str(chunk.get("text", "")) for chunk in data.chunks])
            validate_port("vectors", data.vectors)
        return data
