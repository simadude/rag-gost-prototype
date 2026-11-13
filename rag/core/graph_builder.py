"""Сборка графа исполнения из нод-заглушек (Задача 3 + слой поиска, TASKS.md).

Топология зафиксирована в docs/node-map.md:
- check (основной): user_interface → enforce_security → schedule_checks →
  parse_document → chunk_text → retrieve_fragments (векторный) →
  literal_search (дословный) → graph_search (графовый) → rerank_fragments →
  build_context → distribute_tasks → verify_requirement → format_verdict →
  aggregate_verdicts → compose_report → render_report → handle_followup →
  measure_quality → END
- index (офлайн): user_interface → collect_sources → parse_document →
  chunk_text → embed_chunks → store_vectors → extract_facts → store_facts → END
  (сворачивается в умение prepare_knowledge_base, см. docs/skills-registry.md)
- refresh: user_interface → refresh_corpus → collect_sources → …(как index)
- status: user_interface → system_self_awareness → END (система самознания)
- цикл уточнений: handle_followup → user_interface (если есть вопрос)
- отклонение: enforce_security → END со status="rejected"

Входы разделены: ГОСТы поступают из системы (внутренний источник,
ветка index), документ-решение и запрос — от пользователя (ветка check).
Провайдеры (SQL-БД, база знаний, эмбеддер, LM-провайдер) — за внешним
контуром, доступ только через коннекторы providers/*.

Всё исполняется в среде LangGraph (конституция п.11, TASKS-3 A2):
основной граф — здесь; умения-подграфы — core/skills_registry.py;
одиночные ноды — core/graph_runtime.py (одноузловые подграфы);
исполнение мимо графа исключено стражем «ничего вне графа» (A3).
Сборка графа эмитит события node_added для стражей (core/guards.py):
стражи запускаются методом самого графа по событиям, не по таймеру.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap: модуль должен импортироваться и при запуске напрямую
# (python project/core/graph_builder.py), и как core.graph_builder.
# sys.path[0] при прямом запуске — project/core/, поэтому добавляем project/.
_PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

from langgraph.graph import END, START, StateGraph

from aggregate_verdicts.aggregate_verdicts import AggregateVerdicts
from build_context.build_context import BuildContext
from chunk_text.chunk_text import ChunkText
from collect_sources.collect_sources import CollectSources
from compose_report.compose_report import ComposeReport
from core import graph_context, guards
from core.base_module import BaseModule
from core.data_object import DataObject
from distribute_tasks.distribute_tasks import DistributeTasks
from embed_chunks.embed_chunks import EmbedChunks
from enforce_security.enforce_security import EnforceSecurity
from extract_facts.extract_facts import ExtractFacts
from format_verdict.format_verdict import FormatVerdict
from graph_search.graph_search import GraphSearch
from handle_followup.handle_followup import HandleFollowup
from literal_search.literal_search import LiteralSearch
from measure_quality.measure_quality import MeasureQuality
from parse_document.parse_document import ParseDocument
from refresh_corpus.refresh_corpus import RefreshCorpus
from render_report.render_report import RenderReport
from rerank_fragments.rerank_fragments import RerankFragments
from retrieve_fragments.retrieve_fragments import RetrieveFragments
from schedule_checks.schedule_checks import ScheduleChecks
from store_facts.store_facts import StoreFacts
from store_vectors.store_vectors import StoreVectors
from system_self_awareness.system_self_awareness import SystemSelfAwareness
from user_interface.user_interface import UserInterface
from verify_requirement.verify_requirement import VerifyRequirement


def as_graph_node(module: BaseModule):
    """Обёртка ноды: BaseModule.run(DataObject) как шаг графа LangGraph.

    На время исполнения выставляется контекст графа (`core/graph_context.py`):
    страж «ничего вне графа» (A3) отличает шаг графа от исполнения мимо графа.
    """

    def _step(data: DataObject) -> DataObject:
        with graph_context.graph_step(node_name=module.name):
            return module.run(data)

    _step.__name__ = f"node_{module.name}"
    return _step


# Совместимость: имя, под которым обёртку импортировали умения и смоуки.
_as_graph_node = as_graph_node


# Реестр всех нод графа: одна папка/модуль = одна нода (правило 2).
def _instantiate_nodes() -> dict[str, BaseModule]:
    node_classes = {
        "user_interface": UserInterface,
        "enforce_security": EnforceSecurity,
        "schedule_checks": ScheduleChecks,
        "collect_sources": CollectSources,
        "refresh_corpus": RefreshCorpus,
        "parse_document": ParseDocument,
        "chunk_text": ChunkText,
        "embed_chunks": EmbedChunks,
        "store_vectors": StoreVectors,
        "extract_facts": ExtractFacts,
        "store_facts": StoreFacts,
        "retrieve_fragments": RetrieveFragments,
        "literal_search": LiteralSearch,
        "graph_search": GraphSearch,
        "rerank_fragments": RerankFragments,
        "build_context": BuildContext,
        "distribute_tasks": DistributeTasks,
        "verify_requirement": VerifyRequirement,
        "format_verdict": FormatVerdict,
        "aggregate_verdicts": AggregateVerdicts,
        "compose_report": ComposeReport,
        "render_report": RenderReport,
        "handle_followup": HandleFollowup,
        "measure_quality": MeasureQuality,
        "system_self_awareness": SystemSelfAwareness,
    }
    return {name: cls() for name, cls in node_classes.items()}


def _route_after_user_interface(data: DataObject) -> str:
    """Маршрут прогона, выбранный user_interface (mode).

    Возвращает имя маршрута, а не ноды: сам переход задан в path_map
    ({маршрут: нода}) при add_conditional_edges.
    """
    if data.mode == "index":
        return "index"
    if data.mode == "refresh":
        return "refresh"
    if data.mode == "status":
        return "status"  # система самознания (B2)
    return "check"  # маршрут по умолчанию: enforce_security


def _route_after_enforce_security(data: DataObject) -> str:
    """Отклонённый запрос не проходит дальше по контуру."""
    if data.status == "rejected":
        return END
    return "schedule_checks"


def _route_after_handle_followup(data: DataObject) -> str:
    """Цикл уточнений: с вопросом — обратно к user_interface, без — к метрикам."""
    if data.followup_question:
        return "user_interface"
    return "measure_quality"


def _route_after_chunk_text(data: DataObject) -> str:
    """Ветвление после разбиения на чанки: проверка — в поиск, индексация — в эмбеддинг."""
    if data.mode in ("index", "refresh"):
        return "embed_chunks"
    return "retrieve_fragments"


class GraphApp:
    """Обёртка над скомпилированным графом: invoke() возвращает DataObject.

    LangGraph 1.x с dataclass-схемой состояния возвращает из invoke() dict
    (словарь каналов состояния). Чтобы контракт «по графу ходит единый
    DataObject» не нарушался у потребителей, результат собирается обратно
    в DataObject. Внутри нод объект данных не меняется.
    """

    def __init__(self, app) -> None:
        self._app = app

    def invoke(self, data: DataObject, *args, **kwargs) -> DataObject:
        result = self._app.invoke(data, *args, **kwargs)
        if isinstance(result, DataObject):
            data_out = result
        else:
            data_out = DataObject(**result)
        # Финальный статус: done = прогон дошёл до конца без ошибок и не был
        # отклонён/остановлен. Заглушки нод объект данных не меняют, поэтому
        # нормализация статуса — ответственность обёртки графа.
        if data_out.status == "running" and not data_out.errors:
            data_out.status = "done"
        return data_out

    def stream(self, data: DataObject, *args, **kwargs):
        """Потоковое выполнение: отдает потребителю DataObject-снимки."""
        for chunk in self._app.stream(data, *args, **kwargs):
            if isinstance(chunk, DataObject):
                yield chunk
            elif isinstance(chunk, dict) and all(
                isinstance(v, DataObject) for v in chunk.values()
            ):
                # stream_mode="updates": {имя_ноды: частичное состояние}
                for partial in chunk.values():
                    yield partial
            else:
                yield chunk

    def __getattr__(self, item):  # noqa: D105 - остальное делегируем приложению
        return getattr(self._app, item)


def build_graph():
    """Собирает и компилирует граф исполнения. Возвращает (app, nodes)."""
    guards.register_default_guards()
    nodes = _instantiate_nodes()
    graph = StateGraph(state_schema=DataObject)

    for name, module in nodes.items():
        graph.add_node(name, as_graph_node(module))
        # Событие графа: нода добавилась. Стражи отрабатывают по событиям,
        # не по таймеру («события хорошо, таймеры плохо»).
        guards.emit_graph_event("node_added", node_name=name, module=module)

    # check: основной маршрут
    graph.add_edge("enforce_security", "schedule_checks")
    graph.add_edge("schedule_checks", "parse_document")
    graph.add_edge("parse_document", "chunk_text")
    graph.add_conditional_edges(
        "chunk_text",
        _route_after_chunk_text,
        {"retrieve_fragments": "retrieve_fragments", "embed_chunks": "embed_chunks"},
    )
    graph.add_edge("retrieve_fragments", "literal_search")
    graph.add_edge("literal_search", "graph_search")
    graph.add_edge("graph_search", "rerank_fragments")
    graph.add_edge("rerank_fragments", "build_context")
    graph.add_edge("build_context", "distribute_tasks")
    graph.add_edge("distribute_tasks", "verify_requirement")
    graph.add_edge("verify_requirement", "format_verdict")
    graph.add_edge("format_verdict", "aggregate_verdicts")
    graph.add_edge("aggregate_verdicts", "compose_report")
    graph.add_edge("compose_report", "render_report")
    graph.add_edge("render_report", "handle_followup")
    graph.add_edge("measure_quality", END)

    # status: система самознания — отдельный узел, у которого можно спросить
    graph.add_edge("system_self_awareness", END)

    # index / refresh: офлайн-конвейер индексации
    graph.add_edge("collect_sources", "parse_document")
    graph.add_edge("refresh_corpus", "collect_sources")
    graph.add_edge("embed_chunks", "store_vectors")
    graph.add_edge("store_vectors", "extract_facts")
    graph.add_edge("extract_facts", "store_facts")
    graph.add_edge("store_facts", END)

    # вход и ветвление по маршрутам
    graph.add_edge(START, "user_interface")
    graph.add_conditional_edges(
        "user_interface",
        _route_after_user_interface,
        {
            "check": "enforce_security",
            "index": "collect_sources",
            "refresh": "refresh_corpus",
            "status": "system_self_awareness",
        },
    )
    graph.add_conditional_edges(
        "enforce_security",
        _route_after_enforce_security,
        {"schedule_checks": "schedule_checks", END: END},
    )
    graph.add_conditional_edges(
        "handle_followup",
        _route_after_handle_followup,
        {"user_interface": "user_interface", "measure_quality": "measure_quality"},
    )

    app = graph.compile()
    return GraphApp(app), nodes
