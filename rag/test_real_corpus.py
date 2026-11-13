"""Тесты качества поиска по реальному корпусу (B1, TASKS-3: «на тесты опереться»).

    python3 project/test_real_corpus.py                 # все службы
    python3 project/test_real_corpus.py --db project/var/vectors.db

Корпус: `sto-rules.pdf` (СК-СТО-ТР-04-1.005-2015 — справочник правил оформления,
проиндексирован через граф, чанки в SQLite). Разметка честная: у каждого пункта
справочника есть код «P XX-XX» прямо в тексте чанка — запрос считается
покрытым (hit@k), если в top-k попал чанк, содержащий код целевого пункта.

Службы: llama.cpp (Qwen3-Embedding-4B :8912, EmbeddingGemma-2 :8913,
Qwen3-VL-Embedding-2B :8914). Векторы чанков переэмбеддируются на лету
коннектором службы, чтобы все модели сравнивались на одних и тех же чанках.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from providers.embedder import LlamaCppEmbedder  # noqa: E402

INSTRUCTION_STO = ("Given a search query, retrieve relevant clauses of the Russian university "
                   "standard (СТО) on formatting rules of written works that answer the query")

# Запросы студента/инженера → код целевого пункта справочника (в тексте чанка).
# None у цели — no-match калибровка: релевантного пункта в корпусе нет.
QUERIES: list[tuple[str, str, str | None]] = [
    ("q1", "какие должны быть поля страницы?", "P 01-02"),
    ("q2", "как нумеруются страницы и где стоит номер?", "P 01-03"),
    ("q3", "ставится ли номер страницы на титульном листе?", "P 01-04"),
    ("q4", "какой абзацный отступ?", "P 02-03"),
    ("q5", "какой межстрочный интервал?", "P 02-04"),
    ("q6", "какой интервал между абзацами?", "P 02-05"),
    ("q7", "по какому краю выравнивать текст?", "P 02-02"),
    ("q8", "как подписывать таблицу и нужна ли точка?", "P 08-03"),
    ("q9", "где указывать источник для рисунка?", "P 06-05"),
    ("n1", "какая температура плавления припоя ПОС-40?", None),
]

SERVICES = {
    "qwen3-embedding-4b": {
        "url": "http://127.0.0.1:8912",
        "doc_prompt": "{t}",
        "query_prompt": f"Instruct: {INSTRUCTION_STO}\nQuery: {{q}}",
    },
    "embeddinggemma-2": {
        "url": "http://127.0.0.1:8913",
        "doc_prompt": "title: none | text: {t}",
        "query_prompt": "task: search result | query: {q}",
    },
    "qwen3-embedding-4b-raw": {
        # A/B: без инструкции — замер вклада промпта из карты модели
        "url": "http://127.0.0.1:8912",
        "doc_prompt": "{t}",
        "query_prompt": "{q}",
    },
    "embeddinggemma-2-raw": {
        # A/B: Gemma без шаблонов руководства
        "url": "http://127.0.0.1:8913",
        "doc_prompt": "{t}",
        "query_prompt": "{q}",
    },
    "qwen3-vl-embedding-2b": {
        "url": "http://127.0.0.1:8914",
        # сырой текст: префикс-инструкция рушит VL-модель (см. test_embedder_quality.py)
        "doc_prompt": "{t}",
        "query_prompt": "{q}",
    },
}


def load_chunks(db_path: Path, source: str) -> list[dict]:
    """Все чанки данного источника из SQLite (метаданные — json)."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT metadata FROM vectors").fetchall()
    conn.close()
    chunks = []
    for (raw,) in rows:
        meta = json.loads(raw)
        if source in str(meta.get("source", "")):
            chunks.append(meta)
    return chunks


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def service_alive(url: str) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=3) as response:
            return json.loads(response.read()).get("status") == "ok"
    except Exception:  # noqa: BLE001
        return False


def evaluate(name: str, config: dict, chunks: list[dict]) -> dict | None:
    emb = LlamaCppEmbedder(url=config["url"])
    limits = emb.limits()
    texts = [config["doc_prompt"].format(t=str(chunk.get("text", ""))) for chunk in chunks]
    t0 = time.monotonic()
    doc_vectors = emb.embed(texts)
    index_seconds = time.monotonic() - t0

    rows, hits = [], {1: 0, 3: 0, 5: 0}
    ranks: list[float] = []
    query_times = []
    for qid, qtext, code in QUERIES:
        prompt = config["query_prompt"].format(q=qtext)
        t0 = time.monotonic()
        qvec = emb.embed([prompt])[0]
        query_times.append(time.monotonic() - t0)
        sims = sorted(
            ((cosine(qvec, dv), chunk) for dv, chunk in zip(doc_vectors, chunks)),
            key=lambda pair: -pair[0],
        )
        if code is None:
            rows.append((qid, "—", "—", round(sims[0][0], 3)))
            continue
        rank = next(
            (i for i, (_, chunk) in enumerate(sims, start=1) if code in str(chunk.get("text", ""))),
            None,
        )
        if rank is None:
            rows.append((qid, code, ">всех", round(sims[0][0], 3)))
            continue
        ranks.append(rank)
        for k in hits:
            hits[k] += int(rank <= k)
        rows.append((qid, code, rank, round(sims[rank - 1][0], 3)))

    n = len([r for r in rows if r[2] not in ("—",)])
    mrr = (sum(1.0 / r[2] for r in rows if isinstance(r[2], int)) / n) if n else 0.0
    return {
        "name": name, "chunks": len(chunks), "dim": limits.dim,
        "hit1": hits[1] / n if n else 0, "hit3": hits[3] / n if n else 0,
        "hit5": hits[5] / n if n else 0, "mrr": mrr,
        "index_seconds": round(index_seconds, 1),
        "avg_query_ms": round(sum(query_times) / len(query_times) * 1000),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Качество поиска по реальному корпусу (B1)")
    parser.add_argument("--db", default="project/var/vectors.db")
    parser.add_argument("--source", default="sto-rules.pdf",
                        help="источник-фильтр внутри корпуса (подстрока пути)")
    parser.add_argument("--service", action="append", default=[],
                        help="запустить только выбранные службы (имя из SERVICES)")
    args = parser.parse_args()
    db_path = Path(args.db)
    chunks = load_chunks(db_path, args.source)
    if not chunks:
        print(f"В {db_path} нет чанков источника {args.source!r} — проиндексируй корпус (run_index.py)")
        return 2
    print(f"Корпус: {len(chunks)} чанков из {args.source!r} (БД {db_path})\n")

    configs = dict(SERVICES)
    if args.service:
        configs = {k: v for k, v in SERVICES.items() if k in set(args.service)}

    results = []
    for name, config in configs.items():
        if not service_alive(config["url"]):
            print(f"--- {name}: служба {config['url']} не поднята — пропуск")
            continue
        print(f"--- {name} ({config['url']}) ---")
        result = evaluate(name, config, chunks)
        results.append(result)
        for qid, code, rank, sim in result["rows"]:
            mark = "ok " if rank == 1 else ("~  " if isinstance(rank, int) and rank <= 3 else
                                            "FAIL" if isinstance(rank, int) else "cal")
            print(f"  [{mark}] {qid}: цель {code}, место {rank} (sim {sim})")
        print(f"  hit@1={result['hit1']:.2f} hit@3={result['hit3']:.2f} hit@5={result['hit5']:.2f} "
              f"MRR={result['mrr']:.2f} | переэмбеддинг корпуса {result['index_seconds']} c, "
              f"запрос ~{result['avg_query_ms']} мс | dim={result['dim']}")

    print("\n=== СВОДКА (реальный корпус, 9 запросов) ===")
    for r in results:
        print(f"{r['name']:22s} hit@1={r['hit1']:.2f} hit@3={r['hit3']:.2f} "
              f"hit@5={r['hit5']:.2f} MRR={r['mrr']:.2f} запрос~{r['avg_query_ms']}мс")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
