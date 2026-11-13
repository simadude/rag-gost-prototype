"""Реестр умений: умение = подграф, который можно запустить отдельно (A3).

Лекция 5:36–11:00: «любая цепочка… один линейный конвейер — сворачивается в один
узел… это то, что можно запустить отдельно, и она будет также работать».
Первое умение (пример заказчика): «умение довести сырой документ до входа
в базу» — офлайн-цепочка индексации.

Подграф собирается из **тех же нод** (тех же пакетов), что и основной граф:
умение — не копия кода, а свёртка существующей цепочки. Собранный подграф
возвращается той же обёрткой `GraphApp`, что и основной граф, поэтому контракт
прогона не отличается.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.data_object import DataObject
from core.node_loader import load_node_class


@dataclass(frozen=True)
class SkillDefinition:
    """Описание умения: имя, назначение, сворачиваемая цепочка нод."""

    name: str
    description: str
    chain: tuple[str, ...]   # имена нод по порядку исполнения
    source_mode: str         # маршрут основного графа, который сворачивается в умение


SKILLS: dict[str, SkillDefinition] = {
    "prepare_knowledge_base": SkillDefinition(
        name="prepare_knowledge_base",
        description="Умение довести сырой документ до входа в базу: разбить на чанки, "
                    "получить векторы, записать в SQL-БД, извлечь факты и уложить их "
                    "в базу знаний (свёртка index-ветки).",
        chain=("chunk_text", "embed_chunks", "store_vectors", "extract_facts", "store_facts"),
        source_mode="index",
    ),
}


def build_skill(name: str) -> tuple[object, SkillDefinition]:
    """Собирает умение как самостоятельный граф из тех же нод.

    Подграф — не новая реализация, а та же цепочка нод, собранная отдельно:
    «можно запустить отдельно, и она будет работать так же».
    Импорт graph_builder — ленивый, чтобы не зациклить сборку графа
    (graph_builder импортирует ноду самознания, которая читает реестр умений).
    """
    from langgraph.graph import END, START, StateGraph

    from core.graph_builder import GraphApp, as_graph_node

    definition = SKILLS.get(name)
    if definition is None:
        raise KeyError(f"Умение {name!r} не зарегистрировано в реестре")
    graph = StateGraph(state_schema=DataObject)
    previous: str | None = None
    for node_name in definition.chain:
        module = load_node_class(node_name)()
        graph.add_node(node_name, as_graph_node(module))
        if previous is None:
            graph.add_edge(START, node_name)
        else:
            graph.add_edge(previous, node_name)
        previous = node_name
    graph.add_edge(previous, END)
    return GraphApp(graph.compile()), definition


def run_skill(name: str, data: DataObject | None = None) -> DataObject:
    """Запускает умение отдельно (удобство тестирования умения само по себе)."""
    skill, definition = build_skill(name)
    if data is None:
        data = DataObject(run_id=f"skill-{name}", mode=definition.source_mode)
    result = skill.invoke(data, config={"configurable": {"thread_id": data.run_id}})
    assert not result.errors, f"Ошибки в умении {name}: {result.errors}"
    assert result.trace == list(definition.chain), (
        f"Умение {name} должно проходить по цепочке {definition.chain}, получено {result.trace}"
    )
    return result
