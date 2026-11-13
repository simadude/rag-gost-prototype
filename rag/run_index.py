"""Индексация корпуса через граф (инструмент поверх графа, конституция п.11).

    python3 project/run_index.py --source /путь/к/файлу.pdf --source /путь/к/папке
    RAG_EMBEDDER=llamacpp RAG_EMBEDDER_URL=http://127.0.0.1:8912 \
    RAG_VECTOR_DB=sqlite RAG_SQLITE_PATH=project/var/vectors.db \
    python3 project/run_index.py --source ~/Downloads/sto-rules.pdf

Маршрут index основного графа: user_interface → collect_sources →
parse_document → chunk_text → embed_chunks → store_vectors → extract_facts →
store_facts → END. Всё исполнение — в LangGraph (core/graph_runtime).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from core.data_object import DataObject  # noqa: E402
from core.graph_runtime import invoke_main  # noqa: E402
from providers.embedder import get_embedder  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Индексация корпуса через граф (маршрут index)")
    parser.add_argument("--source", action="append", required=True,
                        help="файл или папка корпуса (можно несколько раз)")
    parser.add_argument("--run-id", default="index-cli")
    args = parser.parse_args()

    limits = get_embedder().limits()
    print(f"Эмбеддер: {limits.model} | dim={limits.dim} | "
          f"входные ворота: {limits.max_input_chars} симв. | батч: {limits.max_batch}")

    data = DataObject(run_id=args.run_id, mode="index", source_files=list(args.source))
    t0 = time.monotonic()
    result = invoke_main(data, mode="index")
    elapsed = time.monotonic() - t0

    print(f"\n=== Прогон index ({elapsed:.1f} с) ===")
    print("trace:", " → ".join(result.trace))
    print(f"файлов: {len(result.source_files)} | документов: {len(result.documents)} | "
          f"чанков: {len(result.chunks)} | векторов: {len(result.vectors)} | "
          f"в БД: {result.stored_count} | фактов: {result.facts_stored}")
    if result.embedder_cuts:
        print("входные ворота разрезали чанков:", len(result.embedder_cuts))
    if result.errors:
        print("ошибки:")
        for error in result.errors:
            print("  -", error)
        return 1
    print("Индексация прошла без ошибок.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
