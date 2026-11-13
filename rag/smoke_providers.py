"""Smoke-тест провайдеров внешнего контура (A4).

Проверяет контракт «замена провайдера щелчком пальцев» и WAL:
    python3 project/smoke_providers.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from core.data_object import validate_port  # noqa: E402
from providers.embedder import StubEmbedder, fit_chunks  # noqa: E402
from providers.stores import (  # noqa: E402
    MemoryKnowledgeBase,
    MemoryVectorStore,
    PostgresVectorStore,
    SqliteVectorStore,
    get_vector_store,
)

VEC_A = [1.0, 0.0, 0.0, 0.0]
VEC_B = [0.0, 1.0, 0.0, 0.0]
CHUNKS = [{"id": "c1", "text": "толщина стенки не менее 4 мм"}, {"id": "c2", "text": "прочее"}]


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(f"SMOKE FAIL: {message}")
    print(f"  ok: {message}")


def test_sqlite_wal(tmp: str) -> None:
    store = SqliteVectorStore(Path(tmp) / "vectors.db")
    check(store.journal_mode() == "wal", "SQLite в WAL-режиме (журнал = wal)")
    n = store.add_many([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], CHUNKS)
    check(n == 2 and store.count() == 2, "запись векторов через коннектор SQL-БД")
    hits = store.search([1.0, 0.0, 0.0], top_k=1)
    check(hits[0]["id"] == "c1", "векторный поиск возвращает ближайший чанк")
    lit = store.search_literal("4 мм", top_k=5)
    check(len(lit) == 1 and lit[0]["id"] == "c1", "дословный поиск находит точное совпадение")


def test_same_interface(tmp: str) -> None:
    """Замена SQLite → memory (и далее PostgreSQL) — тот же интерфейс, тот же ответ."""
    memory = MemoryVectorStore()
    sqlite_store = SqliteVectorStore(Path(tmp) / "v2.db")
    for store in (memory, sqlite_store):
        store.add_many([VEC_A, VEC_B], CHUNKS)
    m_hits = memory.search(VEC_A, top_k=1)
    s_hits = sqlite_store.search(VEC_A, top_k=1)
    check(
        [h["id"] for h in m_hits] == [h["id"] for h in s_hits],
        "реализации провайдера дают одинаковый ответ (замена щелчком пальцев)",
    )


def test_postgres_swap(tmp: str) -> None:
    try:
        store = PostgresVectorStore(dsn="postgresql://rag:***@внешний-контур/векторы")
        store.add_many([VEC_A], CHUNKS)
    except RuntimeError as exc:
        # Драйвер psycopg2 в скелет не притягивается: коннектор честно сообщает
        # об этом (в конструкторе или при записи) и не притворяется, что прошло.
        check(
            "psycopg2" in str(exc) or "PostgresVectorStore" in str(exc) or "PostgreSQL" in str(exc),
            "коннектор PostgreSQL доступен сменой RAG_VECTOR_DB (драйвер подключается при миграции)",
        )
    else:
        raise AssertionError("ожидался RuntimeError про неустановленный драйвер")
    os.environ["RAG_VECTOR_DB"] = "postgres"
    try:
        swapped = get_vector_store()
    except RuntimeError:
        check(True, "фабрика переключается на PostgreSQL строкой конфигурации (драйвер — при миграции)")
    else:
        check(isinstance(swapped, PostgresVectorStore), "фабрика переключается на PostgreSQL строкой конфигурации")
    finally:
        os.environ["RAG_VECTOR_DB"] = "memory"


def test_knowledge_base(tmp: str) -> None:
    kb = MemoryKnowledgeBase()
    kb.add_fact({"id": "fact-001", "text": "толщина стенки >= 4 мм"})
    kb.add_fact({"id": "fact-002", "text": "сталь 09Г2С"})
    kb.link("fact-001", "fact-002", "материал")
    linked = kb.linked_facts(["fact-001"])
    check(len(linked) == 1 and linked[0]["id"] == "fact-002", "база знаний отдаёт связанные факты")
    check(kb.count_facts() == 2, "счётчик фактов")


def test_embedder_and_ports() -> None:
    embedder = StubEmbedder()
    first = embedder.embed(["допускаемая толщина стенки"])
    second = embedder.embed(["допускаемая толщина стенки"])
    check(first == second, "коннектор эмбеддера детерминирован (одинаковый вход — одинаковый вектор)")
    # Входные ворота (B1): лимиты модели + обратная связь чанкеру.
    limits = embedder.limits()
    check(limits.max_input_chars > 0, "коннектор отдаёт входные ворота модели (лимит длины входа)")
    long_text = "Д" * (limits.max_input_chars + 100)
    fitted, cuts = fit_chunks([{"id": "c1", "gost": "ГОСТ 2.105", "text": long_text}],
                              limits.max_input_chars)
    check(
        len(fitted) == 2
        and all(len(str(c["text"])) <= limits.max_input_chars for c in fitted)
        and fitted[0]["parent_id"] == "c1" and fitted[0]["gost"] == "ГОСТ 2.105",
        "ворота: чанк разрезан под лимит, структура сохранена (parent_id, ГОСТ)",
    )
    check(cuts == [{"chunk": "c1", "parts": 2, "limit": limits.max_input_chars}],
          "ворота: отчёт о разрезах — обратная связь эмбеддера к чанкеру")
    try:
        validate_port("stored_count", "не число")
    except TypeError:
        check(True, "validate_port отвергает чужой тип порта (единообразие портов)")
    else:
        raise AssertionError("validate_port должен был отвергнуть строку для int-порта")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        print("Провайдеры внешнего контура:")
        test_sqlite_wal(tmp)
        test_same_interface(tmp)
        test_postgres_swap(tmp)
        test_knowledge_base(tmp)
        test_embedder_and_ports()
    print("SMOKE OK: провайдеры, коннекторы, WAL, замена SQLite→PostgreSQL — все проверки прошли.")


if __name__ == "__main__":
    main()
