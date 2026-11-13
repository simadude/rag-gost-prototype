"""LM-провайдер (API-узел агентов) за внешним контуром (A4, лекция 17:40–21:30).

Агентов в системе «до чёртовой матери», но работают все они через один
свой API-узел — LM-провайдер, который выносится за внешний контур. Понятие
провайдера позволяет безопасно создавать шлюз во внешний контур: ограничение
частоты, учёт расходов и смена модели делаются в одном месте.

К LM-провайдеру ходят (см. docs/agents-map.md): extract_facts, verify_requirement,
aggregate_verdicts (при конфликтах), handle_followup и интеллектуальный страж.
"""
from __future__ import annotations

import json
import os
import urllib.request


class LmProvider:
    """Интерфейс коннектора к LM-провайдеру."""

    def complete(self, prompt: str, system: str = "") -> str:  # noqa: D401
        raise NotImplementedError


class StubLmProvider(LmProvider):
    """Детерминированная заглушка для скелета: не обращается в сеть."""

    def complete(self, prompt, system="") -> str:
        return f"[stub lm] {system} {prompt}".strip()


class HttpLmProvider(LmProvider):
    """HTTP-коннектор к API-узлу LM-провайдера (агенты ходят только отсюда).

    Договор о службе: POST JSON {"prompt": ..., "system": ...} на RAG_LM_URL,
    ответ JSON {"completion": "..."}.
    """

    def __init__(self, url: str | None = None) -> None:
        self._url = url or os.environ.get("RAG_LM_URL", "")
        if not self._url:
            raise RuntimeError(
                "Коннектор LM-провайдера: не задан RAG_LM_URL — "
                "API-узел агентов за внешним контуром не настроен"
            )

    def complete(self, prompt, system="") -> str:
        payload = json.dumps({"prompt": prompt, "system": system}).encode("utf-8")
        request = urllib.request.Request(
            self._url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
        return body["completion"]


class OpenRouterLmProvider(LmProvider):
    """Коннектор к OpenRouter (OpenAI-совместимый /v1/chat/completions).

    Настройка окружением:
    - RAG_LM_MODEL — модель, например z-ai/glm-5.3-flash;
    - RAG_LM_API_KEY — ключ; либо RAG_LM_KEY_FILE — путь к файлу с ключом
      (файл читается в момент вызова). Ключи в репозиторий не кладутся;
    - RAG_LM_MAX_TOKENS — бюджет ответа (по умолчанию 4000: у reasoning-моделей
      часть уходит на размышление).
    """

    DEFAULT_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, model: str | None = None) -> None:
        self._url = os.environ.get("RAG_LM_URL", self.DEFAULT_URL)
        self._model = model or os.environ.get("RAG_LM_MODEL", "z-ai/glm-5.3-flash")
        self._max_tokens = int(os.environ.get("RAG_LM_MAX_TOKENS", "4000"))
        # Учёт расходов на API-узле (лекция: учёт расходов — в одном месте):
        self.total_calls = 0
        self.total_cost = 0.0  # USD, из поля usage.cost ответа OpenRouter

    def _api_key(self) -> str:
        key = os.environ.get("RAG_LM_API_KEY", "")
        if key:
            return key
        path = os.environ.get("RAG_LM_KEY_FILE", "")
        if not path:
            raise RuntimeError(
                "Коннектор OpenRouter: не задан RAG_LM_API_KEY (или RAG_LM_KEY_FILE)"
            )
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()

    def _chat(self, messages: list[dict], max_tokens: int) -> dict:
        payload = json.dumps(
            {"model": self._model, "max_tokens": max_tokens, "messages": messages}
        ).encode("utf-8")
        request = urllib.request.Request(
            self._url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key()}",
            },
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
        error = body.get("error")
        if error:
            raise RuntimeError(f"LM-провайдер OpenRouter: {error}")
        usage = body.get("usage") or {}
        self.total_calls += 1
        self.total_cost += float(usage.get("cost") or 0.0)
        return body

    def complete(self, prompt, system="") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = self._chat(messages, self._max_tokens)
        message = body["choices"][0]["message"]
        if not message.get("content") and message.get("reasoning"):
            # Reasoning-модель съела весь лимит, не успев ответить: повтор с удвоенным бюджетом.
            body = self._chat(messages, self._max_tokens * 2)
            message = body["choices"][0]["message"]
        if not message.get("content"):
            raise RuntimeError("LM-провайдер OpenRouter: модель не вернула текст ответа")
        return message["content"]


def get_lm_provider() -> LmProvider:
    """Фабрика коннектора: RAG_LM_PROVIDER=stub|http|openrouter."""
    backend = os.environ.get("RAG_LM_PROVIDER", "stub").lower()
    if backend == "stub":
        return StubLmProvider()
    if backend == "http":
        return HttpLmProvider()
    if backend == "openrouter":
        return OpenRouterLmProvider()
    raise ValueError(f"Неизвестный LM-провайдер: {backend!r}")
