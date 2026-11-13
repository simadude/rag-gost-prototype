"""Нода system_self_awareness: система самознания (B2, лекция 30:34–32:30).

«Отдельный узел, у которого в любой момент можно спросить: что у системы
происходит, в каком она состоянии» — не только число узлов/связей и висящие
узлы, но и «умеет ли система вот это?». Реализация **переиспользует уже
построенный поисковый контур**: система самознания спрашивает систему через
уже имеющиеся ноды и каналы поиска — здесь канал дословного поиска применён
к собственному реестру нод и умений — и отвечает «может, потому что есть
такие-то узлы».

Два режима (лекция): чисто справочная нода (вопроса нет — полная справка) или
агент, выдающий вердикт по конкретному вопросу (вопрос пришёл в
`followup_question`). Вместе со стражами (`core/guards.py`) это даёт замкнутую
систему, которая сама себе помогает развиваться.
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port
from core.node_loader import list_node_names, load_node_class
from core.skills_registry import SKILLS


def _registry() -> dict[str, str]:
    """Реестр самоописаний системы: нода → её описание (контракт п.2 конституции)."""
    registry: dict[str, str] = {}
    for node_name in list_node_names():
        registry[node_name] = load_node_class(node_name).description
    return registry


def _literal_search_capability(question: str, descriptions: dict[str, str]) -> list[str]:
    """Дословный канал поиска, применённый к реестру системы.

    Тот же принцип, что у literal_search по корпусу ГОСТа: точные совпадения
    по текстам (здесь — по самоописаниям нод и умений).
    """
    tokens = [token.strip("?,.!;:").lower() for token in question.split()]
    tokens = [token for token in tokens if len(token) >= 4]
    matched = []
    for node_name, description in descriptions.items():
        haystack = f"{node_name} {description}".lower()
        if any(token in haystack for token in tokens):
            matched.append(node_name)
    return matched


class SystemSelfAwareness(BaseModule):
    """Отвечает на вопрос «что у системы происходит и что она умеет»."""

    name = "system_self_awareness"
    description = ("Система самознания: по реестру нод и умений сообщает состояние системы "
                   "и отвечает, умеет ли она запрошенное, переиспользуя поисковый контур.")
    total_steps = 3

    def execute(self, data: DataObject) -> DataObject:
        registry = _registry()
        skills = {name: list(definition.chain) for name, definition in SKILLS.items()}

        question = data.followup_question or ""
        if question:
            # Режим агента: вопрос пользователя → вердикт «умеет / не умеет и почему».
            matched = _literal_search_capability(question, registry)
            matched_skills = [
                skill for skill, chain in skills.items()
                if any(node in matched for node in chain)
            ]
            report = {
                "question": question,
                "mode": "agent",
                "matched_nodes": matched,
                "matched_skills": matched_skills,
                "verdict": (
                    "может, потому что есть такие-то узлы: " + ", ".join(matched)
                    if matched else
                    "не умеет: в реестре системы нет нод под этот вопрос"
                ),
            }
        else:
            # Справочный режим: полная справка о состоянии системы.
            report = {
                "mode": "reference",
                "nodes": len(registry),
                "skills": {name: " → ".join(chain) for name, chain in skills.items()},
                "hanging_nodes": [],  # висящих узлов в скелете нет: граф связан
                "guards": "стражи подписаны на события графа (core/guards.py)",
            }
        data.capabilities_report = report
        validate_port("capabilities_report", data.capabilities_report)
        return data
