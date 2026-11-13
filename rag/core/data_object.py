"""Стандарт объекта данных, циркулирующего по графу исполнения.

Единственный тип, который передаётся между нодами (TASKS.md, правило 6):
никаких ad-hoc словарей. Каждое поле заполняет строго одна нода —
источники полей зафиксированы в docs/node-map.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CheckRequest:
    """Задание на проверку одного документа-решения."""

    file_path: str = ""
    target_gosts: list[str] = field(default_factory=list)


@dataclass
class DataObject:
    """Стандартный объект данных, который проходит по всему графу исполнения."""

    run_id: str = ""            # идентификатор прогона
    mode: str = "check"         # "check" | "index" | "refresh" — маршрут, выбранный user_interface
    status: str = "running"     # "running" | "done" | "stopped" | "rejected"

    # --- user_interface / schedule_checks / enforce_security
    request: CheckRequest | None = None  # задание на проверку (решение + целевые ГОСТы)

    # --- collect_sources / refresh_corpus
    source_files: list[str] = field(default_factory=list)  # файлы на индексацию

    # --- parse_document / chunk_text / embed_chunks / store_vectors
    documents: list = field(default_factory=list)  # текст/таблицы/схемы с привязкой к страницам
    chunks: list = field(default_factory=list)     # чанки + метаданные (№ ГОСТа, пункт, редакция)
    vectors: list = field(default_factory=list)    # чанки + векторы
    embedder_cuts: list = field(default_factory=list)  # входные ворота (B1): какие чанки разрезаны под лимит эмбеддера
    stored_count: int = 0                          # сколько записей легло в SQL-БД

    # --- extract_facts / store_facts (слой графового поиска, индексация)
    facts: list = field(default_factory=list)      # факты: числа, утверждения, ограничения
    facts_stored: int = 0                          # сколько фактов легло в графовую базу знаний

    # --- retrieve_fragments / literal_search / graph_search / rerank_fragments / build_context
    candidate_requirements: list = field(default_factory=list)  # top-K кандидатов (векторный поиск)
    literal_hits: list = field(default_factory=list)            # точные совпадения текста и чисел
    graph_candidates: list = field(default_factory=list)        # связанные факты из базы знаний
    selected_requirements: list = field(default_factory=list)   # объединение и реранкинг трёх каналов
    context_pairs: list = field(default_factory=list)           # пары «пункт ГОСТ + фрагмент решения»

    # --- distribute_tasks / verify_requirement / format_verdict / aggregate_verdicts
    tasks: list = field(default_factory=list)        # задачи для агентов проверки
    raw_answers: list = field(default_factory=list)  # сырые ответы LLM
    verdicts: list = field(default_factory=list)     # вердикты по схеме «статус/цитата/исправление»
    summary_verdict: dict | None = None              # сводный вердикт документа

    # --- compose_report / render_report / measure_quality / handle_followup
    report: dict | None = None            # отчёт: пункт ГОСТ / фрагмент / статус / рекомендация
    presentation: dict | None = None      # показанный пользователю отчёт
    metrics: dict | None = None           # метрики качества проверки
    followup_question: str | None = None  # уточнение пользователя (цикл handle_followup → user_interface)

    # --- служебные поля (наблюдаемость, не бизнес-логика)
    trace: list[str] = field(default_factory=list)   # фактический путь прогона по нодам
    errors: list[str] = field(default_factory=list)  # накопленные ошибки нод
    capabilities_report: dict | None = None          # ответ системы самознания (system_self_awareness)


# -------------------------------------------------------------------- порты (единообразие)
# Единообразие портов (лекция 4:22): «если одна нода посылает другой текст — другая
# обязана его съесть; если шлёт более сложный объект — обязана его принять».
# Порт = информационное поле DataObject; тип порта зафиксирован здесь и не может
# меняться нодами. Владелец поля (кто его заполняет) — docs/node-map.md.
PORT_TYPES: dict[str, type] = {
    "run_id": str,
    "mode": str,
    "status": str,
    "request": CheckRequest,
    "source_files": list,
    "documents": list,
    "chunks": list,
    "vectors": list,
    "embedder_cuts": list,
    "stored_count": int,
    "facts": list,
    "facts_stored": int,
    "candidate_requirements": list,
    "literal_hits": list,
    "graph_candidates": list,
    "selected_requirements": list,
    "context_pairs": list,
    "tasks": list,
    "raw_answers": list,
    "verdicts": list,
    "summary_verdict": dict,
    "report": dict,
    "presentation": dict,
    "metrics": dict,
    "followup_question": str,
    "capabilities_report": dict,
    "trace": list,
    "errors": list,
}


def validate_port(name: str, value) -> None:
    """Проверяет соответствие значения типу порта (единообразие портов).

    Нода, отдающая значение в поле DataObject, обязана класть туда тип,
    зафиксированный в PORT_TYPES; иначе нода-потребитель не сможет его «съесть».
    Вызывается нодами-владельцами перед записью и при сборке графа.
    """
    port_type = PORT_TYPES.get(name)
    if port_type is None:
        raise ValueError(f"Неизвестный порт: {name!r} — порт не зафиксирован в PORT_TYPES")
    if value is not None and not isinstance(value, port_type):
        raise TypeError(
            f"Порт {name!r} принимает {port_type.__name__}, "
            f"получено {type(value).__name__} (единообразие портов нарушено)"
        )
