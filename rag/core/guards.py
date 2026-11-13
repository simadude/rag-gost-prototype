"""Стражи: защита принципов конституции силами самой системы (B1, лекция 22:19–28:50).

Ключевые правила лекции:
- **Защита — часть самой системы**: страж живёт на самом графе, а не снаружи.
  Попытки вынести защиту наружу могут удаться, а могут и нет; внедрение в саму
  систему удаётся всегда — её сложно «вырезать» так, чтобы всё осталось работать.
- **Запуск — методом самого графа, по событиям** изменения состояния графа
  (нода добавилась / изменилась), **не по таймеру**. «События хорошо, таймеры
  плохо»: таймаут — зло, на котором система виснет (пример: проверка доступности
  БД с таймаутом 800 000 000 мс).
- Стражей может быть много; каждый защищает одно отдельное свойство.
- Первый **интеллектуальный страж** (новинка ~3–5 месяцев): агент, который
  проверяет, хорошо ли новые/изменённые модули **самоописаны**. Каскад:
  0/10 символов → простой страж (точно плохо); ~200 символов → уже «думать
  надо» — интеллектуальный страж-агент. Наш контракт ≥30 символов — обобщён
  в каскад ниже.

Состав (встреча №3, TASKS-3):
- `NothingOutsideGraphGuard` — **первый обязательный страж** (A3): исполнение
  мимо графа ловится и жёстко возвращается в граф (`core/graph_runtime.py`).
- `DistinctnessGuard` — отличимость модулей (A1): имя + назначение выделяют
  модуль среди всех остальных, дубли описаний бракуются.
- `SelfDescriptionGuard` + `IntelligentSelfDescriptionAgent` — каскад
  самоописанности (B1 TASKS-2).

Страж — обычный модуль по контракту `BaseModule` (тот же стандарт, «по
контракту»), но исполняется не как шаг конвейера, а событиями графа.
"""
from __future__ import annotations

import re

from dataclasses import dataclass

from core.base_module import BaseModule
from core.data_object import DataObject
from providers.lm_provider import get_lm_provider


@dataclass
class GuardVerdict:
    """Вердикт одного стража по одному событию."""

    guard: str
    node: str
    level: str   # "ok" | "warning" | "fail" | "agent-check"
    reason: str


class GraphEventBus:
    """Шина событий графа: стражи подписаны на события, таймеров нет."""

    def __init__(self) -> None:
        self._handlers: dict[str, list] = {}

    def subscribe(self, event: str, handler) -> None:
        self._handlers.setdefault(event, []).append(handler)

    def emit(self, event: str, **payload) -> list[GuardVerdict]:
        verdicts: list[GuardVerdict] = []
        for handler in self._handlers.get(event, []):
            verdicts.extend(handler(event, **payload) or [])
        return verdicts


_BUS = GraphEventBus()
_VERDICTS: list[GuardVerdict] = []

# Реестр отличимости (A1): нормализованное описание → [(имя ноды, исходное описание)].
# Один модуль = одна бизнес-функция; описания модулей не должны совпадать —
# по имени + назначению система (и нейронка) однозначно различает модули.
_DISTINCTNESS_REGISTRY: dict[str, list[tuple[str, str]]] = {}


def _normalize_description(description: str) -> str:
    """Нормализация описания для сравнения различимости (регистр/пробелы)."""
    return re.sub(r"\s+", " ", description.strip().lower())


def emit_graph_event(event: str, **payload) -> list[GuardVerdict]:
    """Единственный способ известить стражей: событие, не таймер."""
    verdicts = _BUS.emit(event, **payload)
    _VERDICTS.extend(verdicts)
    return verdicts


def guard_reports() -> list[GuardVerdict]:
    """Все вердикты стражей с момента старта процесса (для отчёта прогона)."""
    return list(_VERDICTS)


def reset_guard_reports() -> None:
    _VERDICTS.clear()
    _DISTINCTNESS_REGISTRY.clear()


def subscribe_guard(event: str, handler) -> None:
    _BUS.subscribe(event, handler)


class NothingOutsideGraphGuard(BaseModule):
    """Первый обязательный страж: «ничего вне графа» (A3, встреча №3 09:55–10:15).

    Эксперт: «в обязательном порядке первым же стражем, который нужно завести
    и тестировать… ничего вне графа, прям жесточайшим способом загонять его
    обратно». Страж подписан на событие `outside_execution`, которое эмитит
    `core/graph_runtime.force_into_graph` в момент обнаружения исполнения мимо
    графа (прямой `run()`/`execute()` у модуля, скрипт-обход). Работает по
    событиям, не по таймерам (конституция п.10). Возврат в граф делает сам
    механизм исполнения (одноузловой подграф LangGraph); страж фиксирует
    нарушение как fail-вердикт, чтобы его было видно в отчёте прогона.
    """

    name = "guard_nothing_outside_graph"
    description = ("Первый обязательный страж: по событиям графа ловит исполнение, логику и "
                   "скрипты мимо графа и жёстко возвращает их в граф LangGraph (A3).")
    total_steps = 1

    def execute(self, data: DataObject) -> DataObject:
        """На графе конвейера страж не исполняется — он работает по событиям."""
        return data

    def handle(self, event: str, module_name: str = "", caller: str = "", via: str = ""):
        if event != "outside_execution":
            return []
        return [GuardVerdict(
            self.name,
            module_name,
            "fail",
            f"исполнение вне графа (через {via}) — жёстко возвращено в граф; "
            f"место вызова: {caller[-200:]}",
        )]


class DistinctnessGuard(BaseModule):
    """Страж отличимости модулей (A1, встреча №3 04:00–04:43).

    Эксперт: «что нужно обязательно добавить? Отличимость одного модуля от
    другого». Один модуль = одна бизнес-функция; у модуля должно быть
    различимое идентифицирующее описание (имя + назначение), по которому
    система (и нейронка) однозначно различает модули. Страж ведёт реестр
    описаний по событиям `node_added`/`node_changed` и бракует совпадающие —
    неразличимые модули «сольются» и для системы, и для нейронки.
    """

    name = "guard_module_distinctness"
    description = ("Страж отличимости: по событиям графа проверяет, что описание каждого модуля "
                   "различимо — не совпадает с описанием другого модуля (один модуль = одна функция).")
    total_steps = 1

    def execute(self, data: DataObject) -> DataObject:
        """На графе конвейера страж не исполняется — он работает по событиям."""
        return data

    def handle(self, event: str, node_name: str = "", module: BaseModule | None = None):
        description = (getattr(module, "description", "") or "").strip()
        if not description or not node_name:
            return []
        normalized = _normalize_description(description)
        seen = _DISTINCTNESS_REGISTRY.setdefault(normalized, [])
        names = [name for name, _ in seen]
        if node_name not in names:
            if names:
                return [GuardVerdict(
                    self.name,
                    node_name,
                    "fail",
                    f"модуль неразличим: описание дословно совпадает с нодой {names[0]} "
                    "(отличимость нарушена, конституция п.12)",
                )]
            seen.append((node_name, description))
        return []


class SelfDescriptionGuard(BaseModule):
    """Простой страж самоописанности: каскад по длине описания ноды (лекция 28:07).

    Каскад: пустое/≤10 символов — «точно плохо описан» → fail; 11–29 — ниже
    контракта (≥30) → fail; 30–200 — описался по контракту → ok; >200 — «уже
    как-то думать надо» → передача интеллектуальному стражу-агенту.
    """

    name = "guard_self_description"
    description = ("Простой страж самоописанности: по событиям графа проверяет, что описание "
                   "каждой ноды существует, не из десяти символов и держит контракт ≥30 символов.")
    total_steps = 1

    def execute(self, data: DataObject) -> DataObject:
        """На графе конвейера страж не исполняется — он работает по событиям."""
        return data

    def handle(self, event: str, node_name: str = "", module: BaseModule | None = None):
        description = (getattr(module, "description", "") or "").strip()
        length = len(description)
        if length <= 10:
            return [GuardVerdict(self.name, node_name, "fail",
                                 f"описание {length} символов — точно плохо описана")]
        if length < 30:
            return [GuardVerdict(self.name, node_name, "fail",
                                 f"описание {length} символов — ниже контракта (≥30)")]
        if length <= 200:
            return [GuardVerdict(self.name, node_name, "ok",
                                 f"описание {length} символов — по контракту")]
        return [GuardVerdict(self.name, node_name, "agent-check",
                             f"описание {length} символов — передача интеллектуальному стражу")]


class IntelligentSelfDescriptionAgent(BaseModule):
    """Интеллектуальный страж-агент: «хорошо ли нода самоописана» — решает LLM.

    Работает через LM-провайдера за внешним контуром (тот же API-узел, что и
    агенты конвейера). Срабатывает только по событию и только на каскадном
    «agent-check» от простого стража.
    """

    name = "guard_self_description_agent"
    description = ("Интеллектуальный страж-агент: по событиям графа оценивает качество "
                   "самоописания нод с длинными описаниями (>200 символов) через LM-провайдера.")
    total_steps = 1

    def execute(self, data: DataObject) -> DataObject:
        return data

    def handle(self, event: str, node_name: str = "", module: BaseModule | None = None):
        description = (getattr(module, "description", "") or "").strip()
        if len(description) <= 200:
            return []  # каскад: короткие описания — юрисдикция простого стража
        provider = get_lm_provider()
        completion = provider.complete(
            f"оцени качество самоописания ноды: {description}",
            system="интеллектуальный страж",
        )
        level = "ok" if "хорош" in completion or "ok" in completion.lower() else "warning"
        return [GuardVerdict(self.name, node_name, level, f"агент: {completion[:120]}")]


def register_default_guards() -> None:
    """Регистрирует стражей на событиях графа (вызывается при сборке графа).

    Порядок — по поручению эксперта (A3): первым заводится страж
    «ничего вне графа», затем страж отличимости (A1), затем каскад
    самоописанности.
    """
    if not has_subscribers("outside_execution"):
        # A3: первый обязательный страж.
        _BUS.subscribe("outside_execution", NothingOutsideGraphGuard().handle)
    if not has_subscribers("node_added"):
        # A1: страж отличимости модулей.
        distinctness = DistinctnessGuard()
        _BUS.subscribe("node_added", distinctness.handle)
        _BUS.subscribe("node_changed", distinctness.handle)
        # Каскад самоописанности (B1 TASKS-2).
        guard = SelfDescriptionGuard()
        agent = IntelligentSelfDescriptionAgent()
        _BUS.subscribe("node_added", guard.handle)
        _BUS.subscribe("node_changed", guard.handle)
        _BUS.subscribe("node_added", agent.handle)
        _BUS.subscribe("node_changed", agent.handle)


def has_subscribers(event: str) -> bool:
    return bool(_BUS._handlers.get(event))
