"""Маркер «этот шаг исполняется внутри LangGraph» (A2, TASKS-3).

Эксперт (встреча №3, 07:36–10:51): «обязательно нужно дожать до состояния
LangGraph, потому что иначе код расползётся» и «эту схему нельзя тестировать
до того, как всё попадёт в LangGraph, прям нельзя — код прорастёт друг в друга».

Механизм: контекстная переменная, которую выставляет обёртка ноды графа
(`core/graph_builder.as_graph_node`) на время исполнения `module.run(data)`.
Контракт модуля (`core/base_module.BaseModule.run`) проверяет маркер: если
исполнение пришло **мимо** графа — событие стражу «ничего вне графа»
(`core/guards.NothingOutsideGraphGuard`) и жёсткий возврат в граф
(одноузловой подграф LangGraph, `core/graph_runtime.invoke_node`).

ContextVar выбран вместо thread-local: корректен и для синхронного прогона,
и для будущего async-исполнения нод (Pregel LangGraph).
"""
from __future__ import annotations

import contextvars

_inside_graph_step: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "inside_graph_step", default=False
)


def is_inside_graph() -> bool:
    """True, если текущий код исполняется как шаг графа LangGraph."""
    return _inside_graph_step.get()


class graph_step:
    """Контекстный менеджер шага графа: внутри — исполнение «по графу»."""

    def __init__(self, node_name: str = "") -> None:
        self.node_name = node_name
        self._token = None

    def __enter__(self) -> "graph_step":
        self._token = _inside_graph_step.set(True)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        _inside_graph_step.reset(self._token)
        return False
