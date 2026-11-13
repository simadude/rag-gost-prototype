"""Нода verify_requirement: агент проверки: сравнивает один пункт ГОСТа с фрагментом решения через LLM..

Источник в декомпозиции: C2 LLM-агенты. Контракт — docs/module-standard.md.
Агент работает через LM-провайдера за внешним контуром (A4): коннектор
`providers.lm_provider.get_lm_provider()`. Уровень 1 тестирования (A4):
агент — отдельная сущность с чистым контекстом: каждая задача проверяется
своим вызовом LM, без памяти о других задачах.
"""
from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port
from providers.lm_provider import get_lm_provider

_SYSTEM = (
    "Ты — строгий верификатор соответствия технического решения нормативному "
    "документу (ГОСТ/СТО). Ты видишь ОДИН пункт нормативного документа и ОДИН "
    "фрагмент решения. Отвечай только JSON."
)

_PROMPT_TEMPLATE = """Пункт нормативного документа:
{requirement}

Фрагмент решения, который проверяется:
{fragment}

Проверь фрагмент решения на соответствие пункту. Верни строго JSON без пояснений:
{{"status": "compliant|violation|needs_review",
  "quote": "<дословная цитата ИЗ ФРАГМЕНТА РЕШЕНИЯ, по которой виден вердикт>",
  "comment": "<одно предложение: что именно соответствует или нарушается>"}}.

status: compliant — фрагмент соответствует пункту; violation — нарушает;
needs_review — по фрагменту нельзя судить (пункт не про этот фрагмент или данных мало)."""

_ALLOWED_STATUS = {"compliant", "violation", "needs_review"}


def _verdict_prompt(task: dict) -> str:
    requirement = task.get("requirement") or {}
    fragment = task.get("fragment") or {}
    req_text = str(requirement.get("text", "")) if isinstance(requirement, dict) else str(requirement)
    frag_text = str(fragment.get("text", "")) if isinstance(fragment, dict) else str(fragment)
    return _PROMPT_TEMPLATE.format(requirement=req_text, fragment=frag_text)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _verify_one(task: dict) -> dict:
    """Проверка одной задачи: вызов LM с чистым контекстом, разбор JSON-верdictа."""
    answer = ""
    try:
        answer = get_lm_provider().complete(_verdict_prompt(task), system=_SYSTEM)
        start, end = answer.find("{"), answer.rfind("}")
        payload = json.loads(answer[start : end + 1]) if 0 <= start < end else {}
    except Exception as error:  # noqa: BLE001 — сбой службы не роняет весь прогон
        payload = {}
        answer = f"[ошибка LM-провайдера: {error}]"
    requirement = task.get("requirement") or {}
    fragment = task.get("fragment") or {}
    frag_text = str(fragment.get("text", "")) if isinstance(fragment, dict) else str(fragment)
    status = str(payload.get("status", ""))
    quote = str(payload.get("quote", ""))
    # Схемные заполнители ("<...>") от заглушки/обрезанного ответа — не данные.
    if status.startswith("<"):
        status = ""
    if quote.startswith("<"):
        quote = ""
    if status not in _ALLOWED_STATUS:
        status = "needs_review"
    # Анти-галлюцинация: цитата обязана быть дословно во фрагменте решения.
    if quote and _norm(quote) not in _norm(frag_text):
        status = "needs_review"
        quote = ""
    return {
        "task_id": str(task.get("id", "")),
        "gost": str(requirement.get("section", requirement.get("gost", ""))) if isinstance(requirement, dict) else "",
        "status": status,
        "quote": quote,
        "comment": "" if str(payload.get("comment", "")).startswith("<") else str(payload.get("comment", ""))[:300],
        "raw": answer[:500],
    }


class VerifyRequirement(BaseModule):
    """Агент проверки: сравнивает один пункт ГОСТа с фрагментом решения через LLM."""

    name = "verify_requirement"
    description = "Агент проверки: сравнивает один пункт ГОСТа с фрагментом решения через LLM"
    total_steps = 3

    def execute(self, data: DataObject) -> DataObject:
        """Агент проверки: ходка к LM-провайдеру по каждой задаче.

        На холостом прогоне задач нет — объект данных не меняется.
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, "шаг {} из {}: проверка задач через LM-провайдера".format(step, self.total_steps))
            self.pace()
        if data.tasks:
            with ThreadPoolExecutor(max_workers=int(os.environ.get("RAG_VERIFY_WORKERS", "4"))) as pool:
                data.raw_answers = list(pool.map(_verify_one, data.tasks))
            validate_port("raw_answers", data.raw_answers)
            provider = get_lm_provider()
            if getattr(provider, "total_calls", 0):
                print(
                    f"verify_requirement: LM-провайдер {getattr(provider, '_model', '?')}: "
                    f"{provider.total_calls} вызовов, расход ${provider.total_cost:.4f}"
                )
        return data
