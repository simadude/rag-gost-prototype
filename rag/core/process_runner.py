"""Жёсткая останавливаемость: изоляция ноды в отдельном процессе (лекция 3:45).

Кооперативная остановка (Killable, выход между квантами) — первая ступень, но
«не надейтесь, что обычный kill сработает — может не сработать по многим причинам,
одна из них — очень большая фантазия у нейронов». Гарантия «убить на глухо» —
процессная изоляция: нода исполняется в отдельном процессе ОС, и supervisor всегда
может завершить его SIGKILL'ом, что не блокируется ничем.

Инструмент *поверх* графа, а не вместо него (A2, TASKS-3): изоляция процесса —
это средство жёсткой остановки, среда исполнения остаётся LangGraph — внутри
процесса нода исполняется одноузловым подграфом LangGraph
(`core/graph_runtime.invoke_node`). Раньше воркер вызывал `module.run(data)`
напрямую — это было исполнение мимо графа, теперь такое исключено.

Контракт для нод: каждая нода обязана корректно исполняться в изолированном
процессе — не полагаться на глобальное состояние интерпретатора, внешние ресурсы
получать через провайдеров за внешним контуром (коннекторы), останавливаться
кооперативно по request_stop_all().
"""
from __future__ import annotations

import multiprocessing as mp
import time

from core.data_object import DataObject


def _worker(node_name: str, data: DataObject, result_queue) -> None:
    """Тело изолированного процесса: исполнить ноду **по графу** и вернуть объект данных."""
    from core.graph_runtime import invoke_node

    try:
        result = invoke_node(node_name, data)
        result_queue.put(("ok", result))
    except Exception as exc:  # noqa: BLE001 - сбой доедает supervisor
        result_queue.put(("error", f"{type(exc).__name__}: {exc}"))


class NodeProcess:
    """Нода в отдельном процессе ОС с гарантированной жёсткой остановкой."""

    def __init__(self, node_name: str) -> None:
        self.node_name = node_name
        self._proc: mp.Process | None = None
        self._queue = None

    def start(self, data: DataObject) -> "NodeProcess":
        ctx = mp.get_context("fork")
        self._queue = ctx.Queue()
        self._proc = ctx.Process(
            target=_worker, args=(self.node_name, data, self._queue), daemon=True
        )
        self._proc.start()
        return self

    def join(self, timeout: float | None = None):
        """Ждёт завершения. Возвращает ("ok", DataObject) | ("error", строка) | None."""
        if self._proc is None:
            raise RuntimeError("Процесс не запущен")
        self._proc.join(timeout)
        if self._queue.empty():
            return None
        return self._queue.get_nowait()

    @property
    def alive(self) -> bool:
        return bool(self._proc and self._proc.is_alive())

    def hard_kill(self, grace_seconds: float = 0.0, join_timeout: float = 5.0) -> bool:
        """Убить процесс «на глухо».

        Порядок: (опционально) кооперативный запрос между квантами → SIGKILL.
        Возвращает True, если процесс гарантированно мёртв. SIGKILL нельзя
        перехватить и «обойти» — этого не может сделать и «фантазия нейронов».
        """
        if self._proc is None:
            return True
        if grace_seconds > 0 and self._proc.is_alive():
            from core.base_module import request_stop_all

            request_stop_all(f"hard kill {self.node_name}")
            time.sleep(grace_seconds)
        if self._proc.is_alive():
            self._proc.kill()  # SIGKILL
            self._proc.join(join_timeout)
        return not self._proc.is_alive()
