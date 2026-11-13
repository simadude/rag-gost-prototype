"""Нода extract_facts: извлекает из чанков ГОСТа факты: числа, допустимые и запрещённые значения и утверждения.

Источник в декомпозиции: Слой графового поиска (индексация). Контракт — docs/module-standard.md.
A1 (docs/agents-map.md): это **агент** — «что здесь факт» решает LLM. А4 (лекция
17:40–21:30): агент работает через LM-провайдера за внешним контуром — коннектор
`providers.lm_provider.get_lm_provider()`, свой API-узел для всех агентов.

B2: факты И триплеты (субъект–предикат–объект) — триплет упакован в поля факта,
факт хранит дословную цитату (анти-галлюцинация: цитата обязана быть в чанке).
Кэш фактов на диске (project/var/facts_cache.json): повторная индексация того же
чанка не тратит вызовы LM-провайдера заново.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port
from providers.lm_provider import get_lm_provider

_PROMPT_TEMPLATE = """Извлеки из фрагмента нормативного документа факты.

Фрагмент (документ {gost}, пункт {point}):
{chunk}

Для каждого факта верни:
- kind: одно из "число", "допуск", "запрет", "утверждение";
- subject: о чём факт (кратко);
- predicate: отношение или условие;
- object: значение или объект;
- quote: ДОСЛОВНАЯ цитата из фрагмента, содержащая этот факт.

Верни строго JSON без пояснений:
{{"facts": [{{"kind": "...", "subject": "...", "predicate": "...", "object": "...", "quote": "..."}}]}}
Если фактов нет — {{"facts": []}}."""

_FALLBACK_FACT_RE = re.compile(
    r"(?:не менее|не более|не позднее|не допускается|должн[аоы]?|составляет|рав[но]"
    r"|\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)


def _chunk_prompt(chunk: dict) -> str:
    return _PROMPT_TEMPLATE.format(
        gost=chunk.get("section", chunk.get("gost", "")),
        point=", ".join(str(p) for p in chunk.get("pages", [])) or "-",
        chunk=str(chunk.get("text", "")),
    )


def _parse_json_answer(answer: str) -> list[dict]:
    """Достаёт JSON-массив фактов из ответа модели (устойчиво к обёрткам)."""
    start, end = answer.find("{"), answer.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        payload = json.loads(answer[start : end + 1])
    except json.JSONDecodeError:
        return []
    facts = payload.get("facts", [])
    if not isinstance(facts, list):
        return []
    return [f for f in facts if isinstance(f, dict) and f.get("quote")]


def _quote_in_chunk(quote: str, chunk_text: str) -> bool:
    """Анти-галлюцинация: дословная цитата обязана быть в чанке (нормализуем пробелы)."""
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()  # noqa: E731
    return norm(quote) in norm(chunk_text)


def _skeleton_fact(i: int, chunk: dict) -> dict:
    return {
        "id": f"fact-{i:03d}",
        "gost": str(chunk.get("gost", "")),
        "chunk_id": str(chunk.get("id", "")),
        "kind": "утверждение",
        "subject": "фрагмент",
        "predicate": "содержит",
        "object": str(chunk.get("text", ""))[:120],
        "quote": str(chunk.get("text", ""))[:200],
    }


def _extract_one(i: int, chunk: dict, cache: dict | None, cache_path: Path | None) -> dict:
    """Извлекает факты одного чанка: LM-вывод → кэш → скелет-деградация."""
    text = str(chunk.get("text", ""))
    key = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    raw = cache.get(key) if cache is not None else None
    if raw is None:
        provider = get_lm_provider()
        try:
            answer = provider.complete(
                _chunk_prompt(chunk), system="агент извлечения фактов из нормативных документов"
            )
            raw = _parse_json_answer(answer)
        except Exception:  # noqa: BLE001 — деградация к скелету, индексация не падает
            raw = None
        if raw is not None and cache is not None:
            cache[key] = raw
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    if raw is None:  # сбой связи или разбора — деградация к скелету
        raw = [
            {"kind": "утверждение", "subject": "фрагмент", "predicate": "содержит",
             "object": text[:120], "quote": text[:200]}
        ] if _FALLBACK_FACT_RE.search(text) else []
    facts = []
    for j, fact in enumerate(raw, start=1):
        if not _quote_in_chunk(str(fact.get("quote", "")), text):
            continue  # цитата не из чанка — факт бракуется
        facts.append({
            "id": f"fact-{i:03d}-{j:02d}",
            "gost": str(chunk.get("section", chunk.get("gost", ""))),
            "chunk_id": str(chunk.get("id", "")),
            "kind": str(fact.get("kind", "утверждение")),
            "subject": str(fact.get("subject", "")),
            "predicate": str(fact.get("predicate", "")),
            "object": str(fact.get("object", "")),
            "quote": str(fact.get("quote", "")),
        })
    return facts  # пустой список — честный ответ «фактов нет», не мусор


class ExtractFacts(BaseModule):
    """Извлекает из чанков ГОСТа факты: числа, допустимые и запрещённые значения и утверждения."""

    name = "extract_facts"
    description = "Извлекает из чанков ГОСТа факты: числа, допустимые и запрещённые значения и утверждения."
    total_steps = 3

    def execute(self, data: DataObject) -> DataObject:
        """Агент фактов: ходка к LM-провайдеру (API-узел агентов) по каждому чанку.

        На холостом прогоне чанков нет — объект данных не меняется.
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, ("шаг {} из {}: вызов LM-провайдера по чанкам".format(step, self.total_steps)))
            self.pace()
        if data.chunks:
            cache_path = Path(__file__).resolve().parent.parent / "var" / "facts_cache.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache: dict = {}
            if cache_path.exists():
                try:
                    cache = json.loads(cache_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    cache = {}
            with ThreadPoolExecutor(max_workers=int(os.environ.get("RAG_FACTS_WORKERS", "4"))) as pool:
                per_chunk = list(pool.map(
                    lambda item: _extract_one(item[0], item[1], cache, cache_path),
                    enumerate(data.chunks, start=1),
                ))
            data.facts = [fact for chunk_facts in per_chunk for fact in chunk_facts]
            validate_port("facts", data.facts)
            provider = get_lm_provider()
            if getattr(provider, "total_calls", 0):
                print(
                    f"extract_facts: LM-провайдер {getattr(provider, '_model', '?')}: "
                    f"{provider.total_calls} вызовов, расход ${provider.total_cost:.4f}"
                )
        return data
