"""Трёхуровневое тестирование (A4, TASKS-3, встреча №3 10:55–15:37).

Эксперт: «тестировать сначала по одному, потом умениями, а потом целиком».

- **Уровень 1 — модуль.** Модуль тестируется отдельно, **отдельным агентом
  с чистым контекстом**, сформированным специально под задачу модуля
  («не тупой, а с подготовленным контекстом»). Расточительно, но подтверждает,
  что модуль не нулевой и выполняет заявленное.
- **Уровень 2 — умение.** Подграф вызывается как узел LangGraph: система
  смотрит, работает ли, собирает все ошибки и делает несколько циклов правки;
  перед прогоном текст очанковывается.
- **Уровень 3 — целиком.** Полный прогон графа по всем маршрутам.

Всё исполнение — в среде LangGraph (`core/graph_runtime.py`): уровень 1 —
одноузловой подграф, уровень 2 — подграф-умение, уровень 3 — основной граф.

    python3 project/run_tests.py            # все уровни
    python3 project/run_tests.py --level 1  # только модули
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from core import guards  # noqa: E402
from core.data_object import CheckRequest, DataObject  # noqa: E402
from core.graph_runtime import invoke_main, invoke_node  # noqa: E402
from core.node_loader import list_node_names, load_node_class  # noqa: E402
from core.skills_registry import SKILLS, build_skill  # noqa: E402
from providers.lm_provider import get_lm_provider  # noqa: E402

# Подготовленный контекст (вход) под задачу модуля — «не тупой, а с
# подготовленным контекстом»: агент получает ровно тот вход, под который
# модуль заявлен. Пополняется по мере появления реальной логики в нодах.
PREPARED_INPUTS: dict[str, dict] = {
    "embed_chunks": {
        "chunks": [
            {"id": "c1", "gost": "ГОСТ 2.105", "text": "Толщина стенки должна быть не менее 4 мм."},
            {"id": "c2", "gost": "ГОСТ 2.105", "text": "Марка стали для корпуса — 09Г2С."},
        ],
    },
}

# Фактические маршруты прогона (docs/node-map.md) — уровень 3 сверяет граф с картой.
EXPECTED_ROUTES: dict[str, list[str]] = {
    "check": [
        "user_interface", "enforce_security", "schedule_checks", "parse_document",
        "chunk_text", "retrieve_fragments", "literal_search", "graph_search",
        "rerank_fragments", "build_context", "distribute_tasks", "verify_requirement",
        "format_verdict", "aggregate_verdicts", "compose_report", "render_report",
        "handle_followup", "measure_quality",
    ],
    "index": [
        "user_interface", "collect_sources", "parse_document", "chunk_text",
        "embed_chunks", "store_vectors", "extract_facts", "store_facts",
    ],
    "refresh": [
        "user_interface", "refresh_corpus", "collect_sources", "parse_document",
        "chunk_text", "embed_chunks", "store_vectors", "extract_facts", "store_facts",
    ],
    "status": ["user_interface", "system_self_awareness"],
}


def _data(run_id: str, mode: str = "check", **fields) -> DataObject:
    data = DataObject(run_id=run_id, mode=mode,
                      request=CheckRequest(file_path="solution.pdf", target_gosts=["ГОСТ 2.105"]))
    for key, value in fields.items():
        setattr(data, key, value)
    return data


# --------------------------------------------------------------------- уровень 1
def prepared_context(module, data: DataObject) -> str:
    """Чистый контекст отдельного агента, сформированный под задачу модуля."""
    fields = {
        name: len(getattr(data, name))
        for name in ("documents", "chunks", "vectors", "facts")
        if getattr(data, name)
    }
    payload = fields or "пустой холостой вход"
    return (
        f"Ты — отдельный тестировщик с чистым контекстом под задачу одного модуля.\n"
        f"Модуль: {module.name}\nЗаявленная функция: {module.description}\n"
        f"Подготовленный вход: {payload}.\n"
        f"Подтверди одним предложением, что модуль выполняет заявленное на этом входе."
    )


def test_module(node_name: str) -> dict:
    """Уровень 1: модуль отдельно — агент с чистым контекстом + прогон по графу."""
    module = load_node_class(node_name)()
    data = _data(f"level1-{node_name}", **PREPARED_INPUTS.get(node_name, {}))

    agent_reply = get_lm_provider().complete(
        prepared_context(module, data),
        system="тестировщик уровня 1 (модуль): подготовленный контекст, чистая голова",
    )

    result = invoke_node(node_name, data)  # исполнение — по графу (одноузловой подграф)

    failures = []
    if result.status != "done":
        failures.append(f"статус {result.status!r} ≠ done")
    if result.errors:
        failures.append(f"ошибки: {result.errors}")
    if result.trace != [node_name]:
        failures.append(f"trace {result.trace} ≠ [{node_name}]")
    if module.predict(data) < 0:
        failures.append("predict() вернул отрицательную оценку (контракт Predictable)")
    if node_name == "embed_chunks" and PREPARED_INPUTS[node_name]["chunks"]:
        if len(result.vectors) != len(result.chunks):
            failures.append("эмбеддер вернул не по вектору на чанк (входные ворота, B1)")

    return {
        "node": node_name,
        "ok": not failures,
        "agent_reply": agent_reply,
        "failures": failures,
    }


def run_level1() -> list[dict]:
    print("Уровень 1 — модули (отдельно, агент с чистым контекстом, прогон по графу):")
    reports = [test_module(node) for node in list_node_names()]
    for report in reports:
        mark = "ok" if report["ok"] else "FAIL"
        print(f"  [{mark}] {report['node']}: агент: {report['agent_reply'][:80]}")
        if report["failures"]:
            print(f"         провалы: {report['failures']}")
    return reports


# --------------------------------------------------------------------- уровень 2
def run_level2(max_cycles: int = 2) -> list[dict]:
    """Уровень 2: умение как узел LangGraph; ошибки собираются, правки циклами.

    Перед прогоном текст очанковывается (входные ворота эмбеддера, B1):
    чанки готовятся заранее и кладутся в объект данных.
    """
    from providers.embedder import get_embedder

    limits = get_embedder().limits()
    print("Уровень 2 — умения (подграфы LangGraph, циклы правки):")
    print(f"  (очанковано под лимит эмбеддера: {limits.max_input_chars} символов на вход)")
    reports = []
    for name in sorted(SKILLS):
        definition = SKILLS[name]
        chunks = PREPARED_INPUTS["embed_chunks"]["chunks"]
        data = _data(f"level2-{name}", mode=definition.source_mode, chunks=chunks)
        app, _ = build_skill(name)
        cycles: list[dict] = []
        result = None
        for cycle in range(max_cycles + 1):
            result = app.invoke(data, config={"configurable": {"thread_id": data.run_id}})
            if not result.errors:
                break
            cycles.append({"cycle": cycle, "errors": list(result.errors)})
            # Цикл правки: агент с подготовленным контекстом чинит и прогон повторяется.
            get_lm_provider().complete(
                f"умение {name} упало с ошибками {result.errors}; предложи правку",
                system="тестировщик уровня 2 (умение): сбор всех ошибок и циклы правки",
            )
        trace_ok = result.trace == list(definition.chain)
        ok = not result.errors and trace_ok
        reports.append({"skill": name, "ok": ok, "cycles": cycles,
                        "failures": [] if ok else [f"trace={result.trace}", f"errors={result.errors}"]})
        mark = "ok" if ok else "FAIL"
        print(f"  [{mark}] {name}: {' → '.join(result.trace)}")
        if cycles:
            print(f"         циклы правки: {cycles}")
    return reports


# --------------------------------------------------------------------- уровень 3
def run_level3() -> list[dict]:
    print("Уровень 3 — целиком (полный прогон графа, все маршруты):")
    guards.register_default_guards()
    reports = []
    for mode, expected in EXPECTED_ROUTES.items():
        guards.reset_guard_reports()
        result = invoke_main(_data(f"level3-{mode}", mode=mode), mode=mode)
        failures = []
        if result.status != "done":
            failures.append(f"статус {result.status!r}")
        if result.errors:
            failures.append(f"ошибки {result.errors}")
        if result.trace != expected:
            failures.append(f"trace {result.trace} ≠ маршруту из node-map.md")
        guard_fails = [v for v in guards.guard_reports() if v.level == "fail"]
        if guard_fails:
            failures.append(f"стражи: {[f'{v.node}: {v.reason}' for v in guard_fails]}")
        reports.append({"mode": mode, "ok": not failures, "failures": failures})
        mark = "ok" if not failures else "FAIL"
        print(f"  [{mark}] маршрут {mode}: {len(result.trace)} нод, стражи без нарушений")
        if failures:
            print(f"         провалы: {failures}")

    # Инвентаризация (A2): каждая нода проекта — нода графа LangGraph.
    from core.graph_runtime import main_app

    graph_node_names = {n for n in main_app().get_graph().nodes if not n.startswith("__")}
    project_nodes = set(list_node_names())
    missing = project_nodes - graph_node_names
    if missing:
        reports.append({"mode": "inventory", "ok": False,
                        "failures": [f"ноды мимо графа LangGraph: {sorted(missing)}"]})
        print(f"  [FAIL] инвентаризация: ноды мимо графа LangGraph: {sorted(missing)}")
    else:
        reports.append({"mode": "inventory", "ok": True, "failures": []})
        print(f"  [ok] инвентаризация: все {len(project_nodes)} нод проекта — ноды графа LangGraph")
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Трёхуровневое тестирование (A4)")
    parser.add_argument("--level", choices=["1", "2", "3", "all"], default="all")
    args = parser.parse_args()

    guards.register_default_guards()
    results: list[list[dict]] = []
    if args.level in ("1", "all"):
        results.append(run_level1())
    if args.level in ("2", "all"):
        results.append(run_level2())
    if args.level in ("3", "all"):
        results.append(run_level3())

    all_reports = [r for level in results for r in level]
    failed = [r for r in all_reports if not r["ok"]]
    print(f"\nИтог: {len(all_reports) - len(failed)}/{len(all_reports)} проверок прошли.")
    if failed:
        for r in failed:
            print(f"  FAIL: {r.get('node') or r.get('skill') or r.get('mode')}: {r['failures']}")
        return 1
    print("Трёхуровневое тестирование пройдено: модули → умения → целиком.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
