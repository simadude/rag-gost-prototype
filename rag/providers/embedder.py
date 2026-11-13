"""Эмбеддер-служба за внешним контуром (A4, лекция 13:30–21:30; B1 TASKS-3).

Эмбеддинг — «тяжёлая процедура»: чтобы искать по смыслу хорошо, нужен тяжёлый
модельный эмбеддер (Qwen3 Embedding), который жрёт железо. Его выносят за
внешний контур и делают службой: к ней можно присоединиться из нескольких мест
схемы (индексация и поисковый канал), а не только в одной точке. Лёгкие вектора —
компромисс по качеству поиска по смыслу.

Решение встречи №3 (B1, 15:41–23:06): эмбеддер — **специализированный**,
выбирается под конкретную функцию/тематический домен, а не универсальный
мультимодальный. Следствие — **входные ворота**: «не всякий эмбеддер съест
любой объём текста» — коннектор отдаёт лимиты конкретной модели
(`EmbedderLimits`, `Embedder.limits()`), чанкер режет под лимит
(`embed_chunks` ↔ `chunk_text`). В службе (`serve_embedder.py`) лимиты
отдаются GET-ом на `/limits`.

Правильный способ ходить к эмбеддеру — коннектор: `get_embedder()` возвращает
единую точку вызова службы; ноды не знают деталей транспорта.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class EmbedderLimits:
    """Входные ворота конкретной модели (B1): что чанкер обязан учесть."""

    model: str                     # имя модели службы
    dim: int                       # размерность вектора (1024, 768, …)
    max_input_chars: int           # максимальная длина одного входа (символы)
    max_batch: int = 64            # максимальный размер батча


DEFAULT_LIMITS = EmbedderLimits(model="stub", dim=16, max_input_chars=8192, max_batch=64)


def fit_chunks(chunks: list, max_chars: int) -> tuple[list, list]:
    """Входные ворота: режет чанки под лимит входа эмбеддера (обратная связь).

    Возвращает (чанки, разрезы). Чанк длиннее лимита делится на части; структура
    и метаданные сохраняются (не выбрасывать разметку, B1): наследуются gost/пункт
    и проставляется parent_id. Разрезы — отчёт для чанкера: `chunk_text` обязан
    сам читать `Embedder.limits()` и резать под лимит; здесь — страховка
    (последняя линия ворот перед эмбеддингом).
    """
    fitted: list = []
    cuts: list = []
    for chunk in chunks:
        text = str(chunk.get("text", ""))
        if len(text) <= max_chars:
            fitted.append(chunk)
            continue
        parts = [text[i:i + max_chars] for i in range(0, len(text), max_chars)]
        for number, part in enumerate(parts, start=1):
            piece = dict(chunk)
            piece["id"] = f"{chunk.get('id', 'chunk')}#{number}"
            piece["text"] = part
            piece["parent_id"] = chunk.get("id", "chunk")
            fitted.append(piece)
        cuts.append({"chunk": chunk.get("id", "chunk"), "parts": len(parts),
                     "limit": max_chars})
    return fitted, cuts


class Embedder:
    """Интерфейс коннектора к эмбеддер-службе."""

    def embed(self, texts: list[str]) -> list[list[float]]:  # noqa: D401
        raise NotImplementedError

    def limits(self) -> EmbedderLimits:  # noqa: D401
        """Входные ворота модели: лимит длины входа, батч, размерность (B1)."""
        raise NotImplementedError


class StubEmbedder(Embedder):
    """Детерминированная заглушка для скелета: хеш-векторы фиксированной размерности.

    Одинаковый текст — одинаковый вектор (проверяемое свойство коннектора),
    настоящая служба подключается тем же интерфейсом.
    """

    DIM = 16

    def embed(self, texts) -> list[list[float]]:
        vectors = []
        for text in texts:
            raw = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [b / 255.0 for b in raw[: self.DIM]]
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            vectors.append([x / norm for x in vec])
        return vectors

    def limits(self) -> EmbedderLimits:
        return DEFAULT_LIMITS


class HttpEmbedder(Embedder):
    """HTTP-коннектор к службе эмбеддера (Qwen3 Embedding) за внешним контуром.

    Договор о службе: POST JSON {"texts": [...]} на RAG_EMBEDDER_URL,
    ответ JSON {"vectors": [[...], ...]}; GET {url}/limits (опционально) →
    JSON {"limits": {"model", "dim", "max_input_chars", "max_batch"}} —
    входные ворота конкретной модели (B1). Служба, понимающая этот договор:
    `project/serve_embedder.py` (обёртка над локальной моделью).
    """

    def __init__(self, url: str | None = None) -> None:
        self._url = url or os.environ.get("RAG_EMBEDDER_URL", "")
        if not self._url:
            raise RuntimeError(
                "Коннектор эмбеддер-службы: не задан RAG_EMBEDDER_URL — "
                "служба за внешним контуром не настроена"
            )
        self._limits: EmbedderLimits | None = None

    def embed(self, texts) -> list[list[float]]:
        payload = json.dumps({"texts": texts}).encode("utf-8")
        request = urllib.request.Request(
            self._url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        return body["vectors"]

    def limits(self) -> EmbedderLimits:
        if self._limits is not None:
            return self._limits
        try:
            with urllib.request.urlopen(self._url.rstrip("/") + "/limits", timeout=10) as response:
                body = json.loads(response.read().decode("utf-8"))
            raw = body.get("limits", body)
            self._limits = EmbedderLimits(
                model=str(raw.get("model", "unknown")),
                dim=int(raw.get("dim", 0)) or len(self.embed(["проба"])[0]),
                max_input_chars=int(raw.get("max_input_chars", 8192)),
                max_batch=int(raw.get("max_batch", 64)),
            )
        except Exception:  # noqa: BLE001 - служба не отдаёт лимиты: безопасный дефолт
            self._limits = EmbedderLimits(model="http-unknown", dim=0, max_input_chars=8192)
        return self._limits


class LlamaCppEmbedder(Embedder):
    """Коннектор к llama-server (llama.cpp) — служба эмбеддера за внешним контуром.

    Запуск службы (окно — ТОЛЬКО по HF-карте модели; GGUF-метаданные
    (context_length) не гарантия — у SWA-моделей там архитектурный максимум):

        llama-server -m <модель.gguf> --port 8912 --embedding -c <окно из HF-карты> -np 1

    Договор: POST /v1/embeddings {"input": [...]} → {"data": [{"index", "embedding"}]}
    (OpenAI-совместимый); GET /props → {"default_generation_settings": {"n_ctx"}} —
    фактическое окно службы, из него считаются входные ворота. Консервативно
    для русского ~2 символа/токен (замер: 21 600 символов ≈ 8 802 токена).
    """

    CHARS_PER_TOKEN = 2.0   # консервативная оценка для русского корпуса
    HEADROOM_TOKENS = 64    # запас на спецтокены/инструкции запроса
    DEFAULT_BATCH = 32      # батч до первого limits() (и как max_batch после)

    def __init__(self, url: str | None = None) -> None:
        self._url = (url or os.environ.get("RAG_EMBEDDER_URL", "http://127.0.0.1:8912")).rstrip("/")
        self._limits: EmbedderLimits | None = None

    def _post_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Сырой POST /v1/embeddings (без ворот) — транспорт без рекурсии."""
        payload = json.dumps({"input": texts}).encode("utf-8")
        request = urllib.request.Request(
            self._url + "/v1/embeddings", data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=600) as response:
            body = json.loads(response.read().decode("utf-8"))
        data = sorted(body["data"], key=lambda d: d.get("index", 0))
        return [d["embedding"] for d in data]

    def embed(self, texts) -> list[list[float]]:
        # Воротам нужен max_batch; до первого limits() режем консервативным дефолтом
        # (иначе limits() → замер dim → embed() → limits(): рекурсия).
        batch = self._limits.max_batch if self._limits else self.DEFAULT_BATCH
        vectors: list[list[float]] = []
        texts = list(texts)
        for start in range(0, len(texts), batch):
            vectors.extend(self._post_embeddings(texts[start:start + batch]))
        assert len(vectors) == len(texts)
        return vectors

    def limits(self) -> EmbedderLimits:
        if self._limits is not None:
            return self._limits
        with urllib.request.urlopen(self._url + "/props", timeout=30) as response:
            props = json.loads(response.read().decode("utf-8"))
        n_ctx = int(props.get("default_generation_settings", {}).get("n_ctx", 0))
        if not n_ctx:
            raise RuntimeError("llama-server /props не отдал n_ctx — входные ворота не посчитать")
        model = str(props.get("model_alias") or props.get("model_path", "llama-server"))
        dim = len(self._post_embeddings(["проба размерности"])[0])
        max_input_chars = int((n_ctx - self.HEADROOM_TOKENS) * self.CHARS_PER_TOKEN)
        self._limits = EmbedderLimits(
            model=model, dim=dim, max_input_chars=max_input_chars, max_batch=self.DEFAULT_BATCH,
        )
        return self._limits


def get_embedder() -> Embedder:
    """Фабрика коннектора: RAG_EMBEDDER=stub|http|llamacpp."""
    backend = os.environ.get("RAG_EMBEDDER", "stub").lower()
    if backend == "stub":
        return StubEmbedder()
    if backend == "http":
        return HttpEmbedder()
    if backend == "llamacpp":
        return LlamaCppEmbedder()
    raise ValueError(f"Неизвестный эмбеддер: {backend!r}")
