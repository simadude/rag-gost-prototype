"""Провайдер SQL-БД векторов + база знаний и коннекторы к ним.

База данных — не труба и не волшебная палочка, просто способ хранения:
в неё *ходят* и от неё *получают ответы*, сквозь неё ничего не течёт
(лекция 11:10–13:10). База данных и хранилище знаний — разные вещи, и способы
ходить к ним разные (хотя одно опирается на другое):
- SQL-БД — векторы и чанки (векторный и дословный каналы поиска);
- база знаний — факты и связи (графовый канал поиска).

Коннекторы предоставляют один и тот же интерфейс для всех реализаций, поэтому
замена SQLite → PostgreSQL «делается щелчком пальцев» (лекция 18:52) — сменой
`RAG_VECTOR_DB`, без правки нод.

SQLite остаётся рабочим выбором; включён WAL-режим — «разносит во времени
несчастных пользователей» при конкурирующих обращениях. PostgreSQL не спешить
(пока нет ~миллиона запросов в секунду).
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path


def _var_dir() -> Path:
    """Каталог данных по умолчанию: <пакет>/../var — не зависит от cwd и имён."""
    return Path(__file__).resolve().parent.parent / "var"


def _cosine(a: list[float], b: list[float]) -> float:
    """Косинусная близость для скелета (векторная БД без спец-расширений)."""
    num = sum(x * y for x, y in zip(a, b))
    da = sum(x * x for x in a) ** 0.5
    db = sum(x * x for x in b) ** 0.5
    if not da or not db:
        return 0.0
    return num / (da * db)


# ---------------------------------------------------------------- SQL-БД векторов
class VectorStore:
    """Интерфейс провайдера SQL-БД векторов (коннектор для нод)."""

    def add_many(self, vectors: list[list[float]], chunks: list[dict]) -> int:  # noqa: D401
        raise NotImplementedError

    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict]:
        raise NotImplementedError

    def search_literal(self, query_text: str, top_k: int = 5) -> list[dict]:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError


class MemoryVectorStore(VectorStore):
    """Локальный in-memory провайдер (скелет и тесты): тот же интерфейс."""

    def __init__(self) -> None:
        self._rows: list[tuple[list[float], dict]] = []

    def add_many(self, vectors, chunks) -> int:
        n = 0
        for i, vec in enumerate(vectors):
            meta = chunks[i] if i < len(chunks) else {}
            self._rows.append((vec, meta))
            n += 1
        return n

    def search(self, query_vector, top_k=5):
        scored = [(_cosine(query_vector, vec), meta) for vec, meta in self._rows]
        scored.sort(key=lambda item: -item[0])
        return [{"score": round(score, 6), **meta} for score, meta in scored[:top_k]]

    def search_literal(self, query_text, top_k=5):
        hits = [meta for _, meta in self._rows if query_text in str(meta.get("text", ""))]
        return hits[:top_k]

    def count(self) -> int:
        return len(self._rows)


class SqliteVectorStore(VectorStore):
    """SQLite-реализация провайдера с WAL-режимом.

    WAL (`PRAGMA journal_mode=WAL`) позволяет читателям и писателю работать
    параллельно, «разнося во времени несчастных пользователей».
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS vectors ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, dim INTEGER NOT NULL, "
            "vector TEXT NOT NULL, metadata TEXT NOT NULL)"
        )
        self._conn.commit()

    def add_many(self, vectors, chunks) -> int:
        n = 0
        for i, vec in enumerate(vectors):
            meta = chunks[i] if i < len(chunks) else {}
            self._conn.execute(
                "INSERT INTO vectors (dim, vector, metadata) VALUES (?, ?, ?)",
                (len(vec), json.dumps(vec), json.dumps(meta)),
            )
            n += 1
        self._conn.commit()
        return n

    def _all(self) -> list[tuple[list[float], dict]]:
        rows = self._conn.execute("SELECT vector, metadata FROM vectors").fetchall()
        return [(json.loads(v), json.loads(m)) for v, m in rows]

    def search(self, query_vector, top_k=5):
        scored = [(_cosine(query_vector, vec), meta) for vec, meta in self._all()]
        scored.sort(key=lambda item: -item[0])
        return [{"score": round(score, 6), **meta} for score, meta in scored[:top_k]]

    def search_literal(self, query_text, top_k=5):
        hits = []
        for _, meta in self._all():
            if query_text in str(meta.get("text", "")):
                hits.append(meta)
                if len(hits) >= top_k:
                    break
        return hits

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM vectors").fetchone()
        return int(row[0])

    def journal_mode(self) -> str:
        """Фактический режим журнала (проверка WAL в smoke-тесте)."""
        row = self._conn.execute("PRAGMA journal_mode").fetchone()
        return str(row[0])


class PostgresVectorStore(VectorStore):
    """Реализация под PostgreSQL за тем же интерфейсом.

    Драйвер не притягивается в скелет намеренно: коннектор показывает, что
    замена SQLite → PostgreSQL — смена одной строки конфигурации
    (`RAG_VECTOR_DB=postgres`), ноды трогать не нужно.
    """

    def __init__(self, dsn: str = "") -> None:
        self._dsn = dsn or os.environ.get("RAG_POSTGRES_DSN", "")
        try:
            import psycopg2  # noqa: F401
        except ImportError as exc:  # pragma: no cover - демонстрация замены
            raise RuntimeError(
                "Коннектор PostgreSQL: для реального использования установите "
                "psycopg2 (или возьмите другую реализацию VectorStore). "
                f"DSN: {self._dsn or 'не задан (RAG_POSTGRES_DSN)'}"
            ) from exc

    def add_many(self, vectors, chunks) -> int:  # pragma: no cover
        raise RuntimeError("PostgresVectorStore: реализация подключается при миграции")

    def search(self, query_vector, top_k=5):  # pragma: no cover
        raise RuntimeError("PostgresVectorStore: реализация подключается при миграции")

    def search_literal(self, query_text, top_k=5):  # pragma: no cover
        raise RuntimeError("PostgresVectorStore: реализация подключается при миграции")

    def count(self) -> int:  # pragma: no cover
        raise RuntimeError("PostgresVectorStore: реализация подключается при миграции")


def get_vector_store() -> VectorStore:
    """Фабрика коннектора: выбор провайдера переменной RAG_VECTOR_DB."""
    backend = os.environ.get("RAG_VECTOR_DB", "sqlite").lower()
    if backend == "memory":
        return MemoryVectorStore()
    if backend == "sqlite":
        return SqliteVectorStore(os.environ.get("RAG_SQLITE_PATH", str(_var_dir() / "vectors.db")))
    if backend == "postgres":
        return PostgresVectorStore()
    raise ValueError(f"Неизвестный провайдер SQL-БД: {backend!r}")


# ------------------------------------------------------------------ база знаний
class KnowledgeBase:
    """Интерфейс провайдера базы знаний: факты и связи между ними."""

    def add_fact(self, fact: dict) -> None:
        raise NotImplementedError

    def link(self, src_id: str, dst_id: str, relation: str) -> None:
        raise NotImplementedError

    def all_facts(self) -> list[dict]:
        raise NotImplementedError

    def linked_facts(self, fact_ids: list[str]) -> list[dict]:
        raise NotImplementedError

    def count_facts(self) -> int:
        raise NotImplementedError


class MemoryKnowledgeBase(KnowledgeBase):
    """Локальный in-memory провайдер базы знаний (скелет и тесты)."""

    def __init__(self) -> None:
        self._facts: dict[str, dict] = {}
        self._links: list[tuple[str, str, str]] = []

    def add_fact(self, fact) -> None:
        self._facts[fact["id"]] = fact

    def link(self, src_id, dst_id, relation) -> None:
        self._links.append((src_id, dst_id, relation))

    def all_facts(self):
        return list(self._facts.values())

    def linked_facts(self, fact_ids):
        return [self._facts[dst] for src, dst, _ in self._links if src in fact_ids and dst in self._facts]

    def count_facts(self) -> int:
        return len(self._facts)


class SqliteKnowledgeBase(KnowledgeBase):
    """SQLite-реализация базы знаний (тоже WAL: пользуются два канала поиска)."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS facts (id TEXT PRIMARY KEY, text TEXT, metadata TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS links (src TEXT, dst TEXT, relation TEXT)"
        )
        self._conn.commit()

    def add_fact(self, fact) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO facts (id, text, metadata) VALUES (?, ?, ?)",
            (fact["id"], fact.get("text", ""), json.dumps(fact)),
        )
        self._conn.commit()

    def link(self, src_id, dst_id, relation) -> None:
        self._conn.execute(
            "INSERT INTO links (src, dst, relation) VALUES (?, ?, ?)", (src_id, dst_id, relation)
        )
        self._conn.commit()

    def all_facts(self):
        rows = self._conn.execute("SELECT metadata FROM facts").fetchall()
        return [json.loads(m) for (m,) in rows]

    def linked_facts(self, fact_ids):
        rows = self._conn.execute(
            "SELECT metadata FROM facts WHERE id IN (SELECT dst FROM links WHERE src IN (%s))"
            % ",".join("?" * len(fact_ids)),
            fact_ids,
        ).fetchall()
        return [json.loads(m) for (m,) in rows]

    def count_facts(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM facts").fetchone()
        return int(row[0])


def get_knowledge_base() -> KnowledgeBase:
    """Фабрика коннектора базы знаний: выбор провайдера RAG_KNOWLEDGE_DB."""
    backend = os.environ.get("RAG_KNOWLEDGE_DB", "sqlite").lower()
    if backend == "memory":
        return MemoryKnowledgeBase()
    if backend == "sqlite":
        return SqliteKnowledgeBase(
            os.environ.get("RAG_KNOWLEDGE_PATH", str(_var_dir() / "knowledge.db"))
        )
    raise ValueError(f"Неизвестный провайдер базы знаний: {backend!r}")
