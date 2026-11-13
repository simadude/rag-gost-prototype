"""Демо контура проверки через граф (маршрут check, конституция п.11).

    RAG_EMBEDDER=llamacpp RAG_EMBEDDER_URL=http://127.0.0.1:8912 \
    RAG_VECTOR_DB=sqlite RAG_SQLITE_PATH=project/var/vectors.db \
    RAG_LM_PROVIDER=openrouter RAG_LM_MODEL=z-ai/glm-5.3-flash \
    python3 project/run_check_demo.py /путь/к/решению.txt

Маршрут check: user_interface → enforce_security → schedule_checks →
parse_document → chunk_text → retrieve_fragments → literal_search →
graph_search → rerank_fragments → build_context → distribute_tasks →
verify_requirement → format_verdict → aggregate_verdicts → compose_report →
render_report → handle_followup → measure_quality → END.
Агентный слой (verify_requirement) — настоящий, через LM-провайдера;
compose/render/measure — каркасные ноды, отчёт печатается из вердиктов.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from core.data_object import CheckRequest, DataObject  # noqa: E402
from core.graph_runtime import invoke_main  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка решения через граф (маршрут check)")
    parser.add_argument("solution", help="файл с текстом решения (txt/md)")
    parser.add_argument("--run-id", default="check-demo", help="имя прогона (имя файла отчёта)")
    parser.add_argument("--target", action="append", default=[],
                        help="целевой норматив проверки (подстрока имени/кода документа; можно несколько раз)")
    args = parser.parse_args()

    data = DataObject(
        run_id=args.run_id,
        mode="check",
        request=CheckRequest(file_path=args.solution, target_gosts=list(args.target)),
        source_files=[args.solution],
    )
    if args.target:
        print("целевые нормативы:", ", ".join(args.target))
    result = invoke_main(data, mode="check")

    print("trace:", " → ".join(result.trace))
    print(f"чанков решения: {len(result.chunks)} | кандидатур ГОСТ: {len(result.candidate_requirements)}")
    print()
    if not result.verdicts:
        print("верdictов нет — агентный слой не отработал (проверь LM-провайдера)")
        return 1
    print("=== Вердикты ===")
    for verdict in result.verdicts:
        print(f"[{verdict['status']:>12}] {verdict['gost']}")
        if verdict["quote"]:
            print(f"    цитата: {verdict['quote'][:120]!r}")
        if verdict["comment"]:
            print(f"    коммент: {verdict['comment'][:160]}")
    counts: dict[str, int] = {}
    for verdict in result.verdicts:
        counts[verdict["status"]] = counts.get(verdict["status"], 0) + 1
    print("\nИтого:", ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    if result.presentation:
        print(f"Отчёт: {result.presentation.get('path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
