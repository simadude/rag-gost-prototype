"""Холостые прогоны графа из нод-заглушек (Задача 4, TASKS.md + TASKS-2).

Проверяет все четыре маршрута (check / index / refresh / status) на прохождение
без ошибок: нода-заглушка возвращает объект данных без изменений, граф
фиксирует фактический путь прогона в data.trace. Отдельно печатает отчёт
стражей: их вердикты собираются по событиям node_added при сборке графа.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from core import guards  # noqa: E402
from core.data_object import CheckRequest, DataObject  # noqa: E402
from core.graph_builder import build_graph  # noqa: E402


def _run(mode: str) -> DataObject:
    """Холостой прогон графа в заданном маршруте."""
    guards.reset_guard_reports()
    app, nodes = build_graph()
    data = DataObject(
        run_id=f"stub-{mode}",
        mode=mode,
        request=CheckRequest(file_path="solution.pdf", target_gosts=["ГОСТ 2.105"]),
    )
    result = app.invoke(data, config={"configurable": {"thread_id": data.run_id}})
    print(f"\n=== Маршрут {mode} ===")
    print("trace:", " → ".join(result.trace))
    print("status:", result.status, "| errors:", result.errors or "нет")
    for name in dict.fromkeys(result.trace):
        progress = nodes[name].progress()
        print(f"  {name}: {progress.status} шаг {progress.step}/{progress.total_steps}")
    if result.capabilities_report is not None:
        print("  самознание:", json.dumps(result.capabilities_report, ensure_ascii=False)[:300])
    assert not result.errors, f"Ошибки в маршруте {mode}: {result.errors}"
    assert result.status == "done", f"Неверный финальный статус: {result.status}"
    _assert_guards()
    return result


def _assert_guards() -> None:
    """Отчёт стражей: все вердикты по событиям node_added должны быть без fail."""
    fails = [v for v in guards.guard_reports() if v.level == "fail"]
    for verdict in fails:
        print(f"  страж FAIL: {verdict.node}: {verdict.reason}")
    assert not fails, f"Стражи нашли нарушения контракта: {[f'{v.node}: {v.reason}' for v in fails]}"
    agent_checks = [v for v in guards.guard_reports() if v.level == "agent-check"]
    print(f"  стражи: {len(guards.guard_reports())} вердиктов, нарушений нет"
          + (f", интеллектуальный страж смотрел {len(agent_checks)} длинных описаний" if agent_checks else ""))


if __name__ == "__main__":
    for mode in ("check", "index", "refresh", "status"):
        _run(mode)
    print("\nХолостые прогоны: все маршруты прошли без ошибок (стражи — на графе, по событиям).")
