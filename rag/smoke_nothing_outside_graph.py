"""Smoke-тест первого обязательного стража «ничего вне графа» (A3, TASKS-3).

    python3 project/smoke_nothing_outside_graph.py

Проверяет: 1) прямой вызов run()/execute() мимо графа ловится стражем и
исполнение жёстко возвращается в граф (одноузловой подграф LangGraph);
2) обычный прогон графа не даёт ни одного нарушения; 3) изоляция процесса
(run_node/process_runner) исполняет ноду по графу, а не мимо него.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from core import guards, graph_context  # noqa: E402
from core.data_object import CheckRequest, DataObject  # noqa: E402
from core.graph_runtime import invoke_main, invoke_node  # noqa: E402
from core.node_loader import load_node_class  # noqa: E402
from core.process_runner import NodeProcess  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(f"SMOKE FAIL: {message}")
    print(f"  ok: {message}")


def _data(run_id: str) -> DataObject:
    return DataObject(run_id=run_id, mode="check",
                      request=CheckRequest(file_path="solution.pdf", target_gosts=["ГОСТ 2.105"]))


def _outside_fails() -> list[guards.GuardVerdict]:
    return [v for v in guards.guard_reports()
            if v.guard == "guard_nothing_outside_graph" and v.level == "fail"]


def main() -> None:
    guards.register_default_guards()
    guards.reset_guard_reports()

    # 1. Прямой вызов run() мимо графа: страж фиксирует, исполнение идёт по графу.
    module = load_node_class("measure_quality")()
    result = module.run(_data("outside-run"))  # исполнение мимо графа — запрещено
    fails = _outside_fails()
    check(len(fails) == 1 and fails[0].node == "measure_quality",
          "страж «ничего вне графа» зафиксировал прямой вызов run() как нарушение")
    check("жёстко возвращено в граф" in fails[0].reason,
          "вердикт стража: исполнение жёстко возвращено в граф")
    check(result.trace == ["measure_quality"] and result.status == "done",
          "исполнение фактически прошло по одноузловому подграфу LangGraph (trace/status)")
    check(not graph_context.is_inside_graph(), "контекст графа корректно снят после возврата")

    # 2. Прямой вызов execute() мимо графа — тот же жёсткий возврат.
    before = len(_outside_fails())
    module2 = load_node_class("measure_quality")()
    result2 = module2.execute(_data("outside-execute"))
    check(len(_outside_fails()) == before + 1,
          "страж ловит и прямой вызов execute() (скрипт-обход графа)")
    check(result2.trace == ["measure_quality"],
          "execute() мимо графа исполнен по графу, объект данных возвращён вызывающему")

    # 3. Обычный прогон графа: ни одного нарушения.
    guards.reset_guard_reports()
    result3 = invoke_main(_data("inside-graph"), mode="check")
    check(result3.status == "done" and "measure_quality" in result3.trace,
          "полный прогон графа (маршрут check) прошёл штатно")
    check(not _outside_fails(),
          "штатный прогон графа не даёт ни одного события «исполнение вне графа»")

    # 4. Изоляция процесса: внутри процесса нода исполняется по графу.
    guards.reset_guard_reports()
    process = NodeProcess("measure_quality").start(_data("isolated-node"))
    outcome = process.join(timeout=60)
    check(outcome is not None and outcome[0] == "ok" and outcome[1].status == "done",
          "изоляция процесса: нода исполнилась внутри отдельного процесса")
    check(outcome[1].trace == ["measure_quality"],
          "изоляция поверх графа: внутри процесса исполнение шло по подграфу LangGraph")

    print("SMOKE OK: «ничего вне графа» — обходы графа невозможны, всё исполняется в LangGraph.")


if __name__ == "__main__":
    main()
