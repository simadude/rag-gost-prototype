"""Запуск одной ноды: изолированный процесс + исполнение по графу (п.2–3, п.11).

Инструмент *поверх* графа (A2, TASKS-3), подтверждает три свойства конституции:
- модуль — самостоятельный исполняемый пакет: ноду можно исполнить отдельно;
- жёсткая останавливаемость: нода исполняется в изолированном процессе ОС,
  который supervisor может убить SIGKILL'ом «на глухо»;
- всё исполняется в среде LangGraph (п.11): внутри изолированного процесса нода
  исполняется одноузловым подграфом LangGraph (`core/graph_runtime.invoke_node`),
  исполнение мимо графа исключено стражем «ничего вне графа» (A3).

Примеры:
    python3 project/run_node.py store_vectors
    python3 project/run_node.py measure_quality --kill-after 0.2
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from core.data_object import CheckRequest, DataObject  # noqa: E402
from core.node_loader import list_node_names  # noqa: E402
from core.process_runner import NodeProcess  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Исполнить одну ноду в изолированном процессе")
    parser.add_argument("node", help="имя ноды (папки проекта)")
    parser.add_argument("--kill-after", type=float, default=0.0,
                        help="демонстрация жёсткой остановки: убить процесс через N секунд")
    parser.add_argument("--mode", default="check", help="маршрут прогона (check/index/refresh/status)")
    args = parser.parse_args()

    if args.node not in list_node_names():
        print(f"Нода {args.node!r} не найдена. Доступны: {', '.join(list_node_names())}")
        return 2

    data = DataObject(
        run_id=f"node-{args.node}",
        mode=args.mode,
        request=CheckRequest(file_path="solution.pdf", target_gosts=["ГОСТ 2.105"]),
    )

    process = NodeProcess(args.node).start(data)
    if args.kill_after > 0:
        time.sleep(args.kill_after)
        killed = process.hard_kill()
        print(f"{args.node}: изолированный процесс убит «на глухо»: {killed}")
        return 0 if killed else 1

    outcome = process.join(timeout=60)
    if outcome is None:
        print(f"{args.node}: процесс не вернул результат за отведённое время")
        return 1
    status, payload = outcome
    if status == "ok":
        print(f"{args.node}: ок; trace={payload.trace}; статус={payload.status}")
        return 0
    print(f"{args.node}: ошибка — {payload}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
