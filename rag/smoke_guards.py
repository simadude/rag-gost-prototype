"""Smoke-тест стражей (B1): события, не таймеры; каскад самоописанности.

    python3 project/smoke_guards.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from core import guards  # noqa: E402
from core.guards import (  # noqa: E402
    DistinctnessGuard,
    IntelligentSelfDescriptionAgent,
    SelfDescriptionGuard,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(f"SMOKE FAIL: {message}")
    print(f"  ok: {message}")


def main() -> None:
    guard = SelfDescriptionGuard()
    agent = IntelligentSelfDescriptionAgent()

    # Каскад: 0/10 символов — точно плохо; <30 — ниже контракта.
    verdicts = guard.handle("node_added", node_name="x", module=SimpleNamespace(description="короткое"))
    check(verdicts[0].level == "fail", "простой страж: 10 символов — точно плохо (fail)")

    verdicts = guard.handle("node_added", node_name="y",
                            module=SimpleNamespace(description="Нода, которая делает важную работу системы."))
    check(verdicts[0].level == "ok", "простой страж: 30–200 символов — по контракту (ok)")

    long_desc = "Нода с очень подробным описанием. " * 6  # >200 символов
    verdicts = guard.handle("node_added", node_name="z", module=SimpleNamespace(description=long_desc))
    check(verdicts[0].level == "agent-check", "каскад: >200 символов — передача интеллектуальному стражу")

    agent_verdicts = agent.handle("node_added", node_name="z",
                                  module=SimpleNamespace(description=long_desc))
    check(agent_verdicts and agent_verdicts[0].guard == "guard_self_description_agent",
          "интеллектуальный страж-агент выносит вердикт через LM-провайдера")

    # События, не таймеры: node_changed тоже доходит.
    changed = guard.handle("node_changed", node_name="z", module=SimpleNamespace(description="плох"))
    check(changed[0].level == "fail", "событие node_changed обрабатывается тем же стражем")

    # Стражи зарегистрированы на шине событий графа (без таймеров).
    guards.register_default_guards()
    check(guards.has_subscribers("node_added") and guards.has_subscribers("node_changed"),
          "стражи живут на графе и подписаны на события изменения состояния")

    verdicts = guards.emit_graph_event("node_added", node_name="w",
                                       module=SimpleNamespace(description="Валидное описание ноды системы, больше тридцати символов."))
    check(len(verdicts) == 1 and verdicts[0].level == "ok",
          "emit по событию доходит до стражей и возвращает вердикт")

    # Отличимость модулей (A1): имя + назначение выделяют модуль среди остальных.
    guards.reset_guard_reports()
    distinctness = DistinctnessGuard()
    check(distinctness.handle("node_added", node_name="alpha",
                              module=SimpleNamespace(description="Модуль считает метрики качества прогона.")) == [],
          "отличимость: уникальное описание не даёт вердикта")
    verdicts = distinctness.handle("node_added", node_name="beta",
                                   module=SimpleNamespace(description="модуль считает   МЕТРИКИ качества прогона."))
    check(verdicts and verdicts[0].level == "fail" and "неразличим" in verdicts[0].reason,
          "отличимость: дубль описания (даже в другом регистре/пробелах) бракуется")
    check(distinctness.handle("node_changed", node_name="alpha",
                              module=SimpleNamespace(description="Модуль считает метрики качества прогона.")) == [],
          "отличимость: повторная регистрация той же ноды не нарушение")
    guards.reset_guard_reports()

    # Страж «ничего вне графа» (A3) зарегистрирован первым.
    guards.register_default_guards()
    check(guards.has_subscribers("outside_execution"),
          "страж «ничего вне графа» подписан на событие outside_execution")
    verdicts = guards.emit_graph_event("outside_execution", module_name="rogue",
                                       caller="some_script.py:1", via="run")
    check(verdicts and verdicts[0].guard == "guard_nothing_outside_graph"
          and verdicts[0].level == "fail",
          "событие outside_execution доходит до первого обязательного стража")
    guards.reset_guard_reports()
    print("SMOKE OK: стражи работают по событиям графа, каскад самоописанности и отличимость исправны.")


if __name__ == "__main__":
    main()
