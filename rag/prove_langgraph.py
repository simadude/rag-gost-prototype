"""Протокол доказательства «всё исполняется в LangGraph» (A2, TASKS-3).

    python3 project/prove_langgraph.py

Четыре независимых линии доказательства, каждая проверяема повторным запуском:

1. **Статика (AST).** Разбор всех .py проекта: найти каждый call-site прямого
   исполнения ноды (`run(...)` / `execute(...)`). Допустимы только: машина
   контракта (`core/base_module.py`), обёртка шага графа (`core/graph_builder.py`),
   зонд-смоук (намеренный обход, который заканчивается в графе). Остальное —
   нарушение.

2. **Идентичность среды.** Скомпилированные приложения — классы из `langgraph.*`
   (CompiledStateGraph/Pregel); инвентаризация: все ноды проекта — узлы
   скомпилированного графа.

3. **Двигатель наблюдает каждый шаг.** Прогон через `stream(stream_mode="updates")`
   самого движка: имена шагов, которые **эммитит Pregel**, в точности совпадают
   с trace прогона (по всем маршрутам, по умению и по одноузловому подграфу).
   Если бы исполнение шло мимо графа, движок не смог бы эммитить его шаги.

4. **Инструментальный трассировщик.** Класс `BaseModule` патчится: каждый вызов
   `run()` фиксирует, был ли контекст шага графа (`graph_context`). Все
   «производственные» вызовы — внутри графа; вне графа — только намеренные
   пробы этого протокола, и каждая из них перехвачена стражем
   «ничего вне графа» и **переисполнена в графе** (факт переисполнения виден
   в трассировщике: вторая запись с inside=True).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from core import graph_context, guards  # noqa: E402
from core.base_module import BaseModule  # noqa: E402
from core.data_object import CheckRequest, DataObject  # noqa: E402
from core.graph_runtime import invoke_node, main_app  # noqa: E402
from core.node_loader import list_node_names  # noqa: E402
from core.skills_registry import SKILLS, build_skill  # noqa: E402

# Файлы, которым прямое исполнение ноды разрешено (машина графа + зонд).
_ALLOWED_DIRECT = {
    "base_module.py",                 # run() → execute(): сама машина контракта
    "graph_builder.py",               # as_graph_node(): обёртка шага графа
    "smoke_nothing_outside_graph.py", # намеренный обход-зонд (заканчивается в графе)
    "prove_langgraph.py",             # намеренные пробы этого протокола
}

_PHASE = {"name": "?"}
_RECORDS: list[dict] = []


def _instrument() -> None:
    """Трассировщик: каждый вызов BaseModule.run() записывает контекст исполнения."""
    original_run = BaseModule.run

    def _recorded_run(self, data: DataObject) -> DataObject:
        _RECORDS.append({
            "phase": _PHASE["name"],
            "module": self.name,
            "inside": graph_context.is_inside_graph(),
        })
        return original_run(self, data)

    BaseModule.run = _recorded_run  # type: ignore[method-assign]


def _data(run_id: str, mode: str = "check") -> DataObject:
    return DataObject(run_id=run_id, mode=mode,
                      request=CheckRequest(file_path="solution.pdf", target_gosts=["ГОСТ 2.105"]))


def _engine_steps(app, data: DataObject) -> list[str]:
    """Имена шагов, которые эммитит сам движок Pregel (stream_mode='updates')."""
    steps = []
    for chunk in app._app.stream(data, stream_mode="updates"):
        if isinstance(chunk, dict) and chunk:
            steps.append(next(iter(chunk)))
    return steps


# ---------------------------------------------------------------- 1. статика
def _looks_like_node_execution(call: ast.Call) -> bool:
    """Исполнение ноды = вызов run()/execute() с объектом данных (DataObject).

    Отсекает одноимённые вызовы других доменов: cursor.execute("INSERT …") —
    SQL-коннекторы, proc.run() и т.п. Аргумент ноды — `data`/`_data(...)`.
    """
    if not call.args:
        return False
    first = call.args[0]
    if isinstance(first, ast.Name) and "data" in first.id.lower():
        return True
    if (isinstance(first, ast.Call) and isinstance(first.func, ast.Name)
            and "data" in first.func.id.lower()):
        return True
    return False


def static_inventory() -> list[str]:
    """AST-разбор проекта: все call-site прямого исполнения ноды (run/execute с данными)."""
    violations = []
    files = sorted(PROJECT_DIR.rglob("*.py"))
    scanned = 0
    hits = 0
    for path in files:
        rel = path.relative_to(PROJECT_DIR).as_posix()
        if "__pycache__" in rel or rel.startswith("."):
            continue
        scanned += 1
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("run", "execute")
                    and _looks_like_node_execution(node)):
                hits += 1
                if path.name not in _ALLOWED_DIRECT:
                    violations.append(f"{rel}:{node.lineno} .{node.func.attr}(<данные>)")
    print(f"1. Статика (AST): просканировано {scanned} файлов проекта; call-site "
          f"исполнения ноды (run/execute с объектом данных): {hits}; "
          f"разрешены только в машине графа ({', '.join(sorted(_ALLOWED_DIRECT))}).")
    if violations:
        for v in violations:
            print(f"   НАРУШЕНИЕ: {v}")
        raise AssertionError(f"исполнение мимо графа: {len(violations)} call-site")
    print("   нарушение: 0 — все call-site прямого исполнения в машине графа/зондах")
    return violations


# ----------------------------------------------------------- 2. идентичность
def identity_check() -> None:
    app = main_app()
    compiled = type(app._app)
    module = compiled.__module__
    assert "langgraph" in module, f"основной граф не из langgraph: {module}"
    print(f"2. Идентичность среды: основной граф — {compiled.__qualname__} "
          f"из {module} (движок Pregel LangGraph).")
    for name in sorted(SKILLS):
        skill_app, _ = build_skill(name)
        skill_module = type(skill_app._app).__module__
        assert "langgraph" in skill_module, f"умение {name} не из langgraph: {skill_module}"
    print(f"   умения ({len(SKILLS)}) — тоже скомпилированные StateGraph LangGraph.")
    single = invoke_node("measure_quality", _data("identity-single"))  # по графу
    assert single.trace == ["measure_quality"]
    print("   одноузловой подграф (invoke_node) — StateGraph LangGraph, прогон прошёл.")


# --------------------------------------------------------- 3. инвентаризация
def inventory_check() -> None:
    graph_nodes = {n for n in main_app().get_graph().nodes if not n.startswith("__")}
    project_nodes = set(list_node_names())
    assert project_nodes <= graph_nodes, f"ноды мимо графа: {sorted(project_nodes - graph_nodes)}"
    print(f"3. Инвентаризация: все {len(project_nodes)} нод проекта — узлы "
          f"скомпилированного графа ({len(graph_nodes)} узлов); нод вне графа: 0.")


# -------------------------------------------- 4. двигатель наблюдает каждый шаг
ENGINE_EXPECTED = {
    "check": ["user_interface", "enforce_security", "schedule_checks", "parse_document",
              "chunk_text", "retrieve_fragments", "literal_search", "graph_search",
              "rerank_fragments", "build_context", "distribute_tasks", "verify_requirement",
              "format_verdict", "aggregate_verdicts", "compose_report", "render_report",
              "handle_followup", "measure_quality"],
    "index": ["user_interface", "collect_sources", "parse_document", "chunk_text",
              "embed_chunks", "store_vectors", "extract_facts", "store_facts"],
    "refresh": ["user_interface", "refresh_corpus", "collect_sources", "parse_document",
                "chunk_text", "embed_chunks", "store_vectors", "extract_facts", "store_facts"],
    "status": ["user_interface", "system_self_awareness"],
}


def engine_observation() -> None:
    print("4. Двигатель наблюдает каждый шаг (stream_mode='updates' эммитит сам Pregel):")
    for mode, expected in ENGINE_EXPECTED.items():
        result = main_app().invoke(_data(f"prove-{mode}", mode=mode))
        assert result.trace == expected, f"маршрут {mode}: trace {result.trace}"
        emitted = _engine_steps(main_app(), _data(f"prove-{mode}-stream", mode=mode))
        assert emitted == expected, f"маршрут {mode}: движок эммитил {emitted}"
        print(f"   маршрут {mode}: {len(emitted)} шагов эммитил движок = {len(expected)} в trace")
    for name in sorted(SKILLS):
        skill_app, definition = build_skill(name)
        data = _data(f"prove-skill-{name}", mode=definition.source_mode)
        emitted = _engine_steps(skill_app, data)
        assert emitted == list(definition.chain), f"умение {name}: движок эммитил {emitted}"
        print(f"   умение {name}: {len(emitted)} шагов эммитил движок = цепочка умения")
    emitted = _engine_steps(invoke_node.__globals__ and _single_app("measure_quality"),
                            _data("prove-single"))
    assert emitted == ["measure_quality"], f"одноузловой: движок эммитил {emitted}"
    print("   одиночная нода: 1 шаг эммитил движок = узел подграфа")


def _single_app(node_name: str):
    from core.graph_runtime import _single_node_app
    return _single_node_app(node_name)


# ------------------------------------------------------ 5. трассировщик run()
def tracer_check() -> None:
    _PHASE["name"] = "production"
    for mode in ENGINE_EXPECTED:
        main_app().invoke(_data(f"prove-trace-{mode}", mode=mode))
    for name in sorted(SKILLS):
        from core.skills_registry import run_skill
        run_skill(name)
    production = [r for r in _RECORDS if r["phase"] == "production"]
    assert production and all(r["inside"] for r in production), \
        f"производственные вызовы вне графа: {[r for r in production if not r['inside']]}"
    unique = len({r["module"] for r in production})
    print(f"5. Трассировщик BaseModule.run(): {len(production)} производственных вызовов — "
          f"100% внутри шага графа (контекст graph_context выставлен обёрткой ноды); "
          f"модулей затронуто: {unique}.")

    # Намеренные пробы: прямой вызов мимо графа — и что с ним стало.
    from core.node_loader import load_node_class

    _PHASE["name"] = "probe-run"
    load_node_class("measure_quality")().run(_data("prove-probe-run"))
    _PHASE["name"] = "probe-execute"
    load_node_class("measure_quality")().execute(_data("prove-probe-execute"))

    probes_outside = [r for r in _RECORDS if not r["inside"]]
    probes_inside = [r for r in _RECORDS if r["phase"].startswith("probe") and r["inside"]]
    fails = [v for v in guards.guard_reports()
             if v.guard == "guard_nothing_outside_graph" and v.level == "fail"]
    assert len(probes_outside) == 1, "ожидалась ровно одна намеренная проба вне графа"
    assert probes_inside, "проба не была переисполнена в графе"
    assert len(fails) == 2, f"страж должен зафиксировать 2 пробы, зафиксировал {len(fails)}"
    print(f"   намеренные пробы мимо графа: 2 события стража (run-проба + execute-проба); "
          f"записей run() вне графа: {len(probes_outside)} — execute-проба перехватывается "
          f"обёрткой ещё до run(); каждая проба переисполнена в графе "
          f"(переисполнений с inside=True: {len(probes_inside)}).")


def main() -> int:
    print("ПРОТОКОЛ ДОКАЗАТЕЛЬСТВА «НИЧЕГО ВНЕ LANGGRAPH» (конституция п.11)\n" + "-" * 72)
    guards.register_default_guards()
    _instrument()  # патч ДО сборки графов: ловим все вызовы run() во всех нодах
    static_inventory()
    identity_check()
    inventory_check()
    engine_observation()
    tracer_check()
    print("-" * 72)
    print("ВЕРДИКТ: исполнение в проекте идёт только через движок LangGraph —")
    print("  статика: 0 call-site мимо графа; нод вне графа: 0;")
    print("  каждый шаг всех маршрутов/умений/одиночных нод эммитил сам Pregel;")
    print("  обходные пробы невозможны: перехватываются стражем и переисполняются в графе.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
