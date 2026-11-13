"""Единая точка исполнения: всё работает в среде LangGraph (A2, TASKS-3).

Эксперт (встреча №3, 07:36–10:51): «эту схему нельзя тестировать до того,
как всё попадёт в LangGraph… код прорастёт друг в друга». Инвентаризация
исполнения мимо графа и её закрытие:

- `run_node.py` + `core/process_runner.py` исполняли ноду напрямую
  (`module.run(data)` в изолированном процессе) — **мимо** графа. Теперь
  изоляция процесса остаётся средством жёсткой остановки (SIGKILL), но
  исполняется нода **по графу**: одноузловой подграф START → нода → END
  (`invoke_node`).
- смоуки и тесты (`run_tests.py`) — инструменты *поверх* графа: запускают
  граф/подграфы через этот модуль, а не вместо него.
- умения (`core/skills_registry.py`) и основной граф (`core/graph_builder.py`)
  уже собираются как StateGraph LangGraph — доступ к ним единообразно через
  `invoke_skill` / `invoke_main`.

Каждый компилированный граф кешируется: сборка — один раз на процесс.
"""
from __future__ import annotations

import traceback

from core.data_object import DataObject
from core.node_loader import list_node_names, load_node_class

_MAIN_APP = None
_NODE_APPS: dict[str, object] = {}


def main_app():
    """Скомпилированный основной граф (кешируется). Возвращает GraphApp."""
    global _MAIN_APP
    if _MAIN_APP is None:
        from core.graph_builder import build_graph

        _MAIN_APP, _ = build_graph()
    return _MAIN_APP


def invoke_main(data: DataObject, mode: str | None = None) -> DataObject:
    """Полный прогон основного графа (маршруты check/index/refresh/status)."""
    if mode is not None:
        data.mode = mode
    return main_app().invoke(data, config={"configurable": {"thread_id": data.run_id or "main"}})


def _single_node_app(node_name: str):
    """Собирает одноузловой подграф START → нода → END из тех же нод.

    Нода — та же (тот же пакет, тот же класс, `core/node_loader.py`): одноузловой
    подграф — не копия кода, а способ исполнить ноду в среде LangGraph.
    """
    from langgraph.graph import END, START, StateGraph

    from core.graph_builder import GraphApp, as_graph_node

    module = load_node_class(node_name)()
    graph = StateGraph(state_schema=DataObject)
    graph.add_node(node_name, as_graph_node(module))
    graph.add_edge(START, node_name)
    graph.add_edge(node_name, END)
    return GraphApp(graph.compile())


def invoke_node(node_name: str, data: DataObject) -> DataObject:
    """Исполняет одну ноду **по графу** (одноузловой подграф LangGraph).

    Используется изоляцией процесса (`core/process_runner.py`), уровнем 1
    трёхуровневого тестирования (`run_tests.py`) и стражем «ничего вне графа»
    как жёсткий возврат исполнения в граф.
    """
    if node_name not in list_node_names():
        raise KeyError(f"Нода {node_name!r} не найдена (папки project/<нода>)")
    app = _NODE_APPS.get(node_name)
    if app is None:
        app = _single_node_app(node_name)
        _NODE_APPS[node_name] = app
    thread_id = data.run_id or f"node-{node_name}"
    return app.invoke(data, config={"configurable": {"thread_id": thread_id}})


def invoke_skill(name: str, data: DataObject | None = None) -> DataObject:
    """Исполняет умение (подграф) через реестр умений — тоже среда LangGraph."""
    from core.skills_registry import run_skill

    return run_skill(name, data)


def force_into_graph(module, data: DataObject, via: str = "run") -> DataObject:
    """Жёсткий возврат исполнения в граф (страж «ничего вне графа», A3).

    Вызывается, когда исполнение пришло мимо графа (прямой вызов `run()` /
    `execute()` у модуля): 1) событие `outside_execution` — стражу; 2) исполнение
    перенаправляется в одноузловой подграф LangGraph — «жесточайшим способом
    загоняем его обратно» (встреча №3, 09:55–10:15).
    """
    from core import guards

    caller = " ← ".join(line.strip() for line in traceback.format_stack(limit=6)[:-1])
    guards.emit_graph_event(
        "outside_execution", module_name=module.name, caller=caller, via=via
    )
    return invoke_node(module.name, data)
