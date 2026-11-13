"""Базовый контракт модуля: Killable / Throttleable / Observable / Semantically identifiable / Distinct.

Каждая нода графа наследует BaseModule. Полный контракт описан в docs/module-standard.md.

Исполнение — только в среде LangGraph (конституция п.11, A2): `run()` и
`execute()`, вызванные **мимо** графа, перехватываются стражем «ничего вне
графа» (A3) и жёстко перенаправляются в одноузловой подграф LangGraph
(`core/graph_runtime.force_into_graph`). Контекст графа — `core/graph_context.py`.
"""
from __future__ import annotations

import abc
import functools
import re
import threading
import time
from dataclasses import dataclass
from typing import ClassVar

from core import graph_context
from core.data_object import DataObject

# Запрещённые «бессмысленные» имена (TASKS.md, правило 3: имя ноды должно
# само по себе объяснять, что она делает).
_BANNED_NAMES = {"node_1", "module_a", "utils_2", "utils", "helpers", "misc", "common", "temp"}
_NAME_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")


class ModuleStopped(Exception):
    """Штатная (кооперативная) остановка модуля. Не является ошибкой выполнения."""

    def __init__(self, module_name: str, reason: str = "") -> None:
        super().__init__(f"Модуль '{module_name}' штатно остановлен: {reason or 'без причины'}")
        self.module_name = module_name
        self.reason = reason


@dataclass(frozen=True)
class Progress:
    """Снимок состояния модуля (основа статус-бара и оркестрации)."""

    status: str                      # idle | running | finished | stopped | failed
    step: int
    total_steps: int
    message: str
    elapsed_seconds: float
    eta_seconds: float | None


_ACTIVE_MODULES: set["BaseModule"] = set()
_ACTIVE_LOCK = threading.Lock()


def request_stop_all(reason: str = "") -> None:
    """Штатная остановка всех работающих модулей (killable на уровне графа)."""
    with _ACTIVE_LOCK:
        targets = tuple(_ACTIVE_MODULES)
    for module in targets:
        module.request_stop(reason)


def _make_gated_execute(execute_impl):
    """Обёртка execute(): прямой вызов мимо графа жёстко возвращается в граф (A3)."""

    @functools.wraps(execute_impl)
    def _gated(self, data: DataObject, *args, **kwargs):
        if graph_context.is_inside_graph():
            return execute_impl(self, data, *args, **kwargs)
        from core.graph_runtime import force_into_graph

        return force_into_graph(self, data, via="execute")

    _gated._graph_gate = True  # маркер: обёртка уже надета
    return _gated


class BaseModule(abc.ABC):
    """Базовый контракт ноды графа исполнения."""

    name: ClassVar[str] = ""          # == имя папки модуля (semantically identifiable)
    description: ClassVar[str] = ""   # различимое идентифицирующее описание (отличимость)
    total_steps: ClassVar[int] = 1
    throttle_delay_seconds: float = 0.0

    _BANNED_NAMES: ClassVar[frozenset[str]] = frozenset(_BANNED_NAMES)
    _NAME_RE: ClassVar[re.Pattern[str]] = _NAME_RE

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        name = getattr(cls, "name", "")
        if not name or not cls._NAME_RE.fullmatch(name):
            raise ValueError(
                f"Имя модуля должно быть осмысленным snake_case, получено: {name!r}"
            )
        if name in cls._BANNED_NAMES:
            raise ValueError(
                f"Запрещено бессмысленное имя модуля: {name!r} (TASKS.md, правило 3)"
            )
        description = getattr(cls, "description", "")
        if len(description.strip()) < 30:
            raise ValueError(
                f"Описание модуля '{name}' должно объяснять назначение (мин. 30 символов)"
            )
        # «Ничего вне графа» (A3): даже прямой вызов execute() идёт через граф.
        execute_impl = cls.__dict__.get("execute")
        if execute_impl is not None and not getattr(execute_impl, "_graph_gate", False):
            cls.execute = _make_gated_execute(execute_impl)

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._stop_reason = ""
        self._lock = threading.Lock()
        self._step = 0
        self._message = ""
        self._status = "idle"   # idle | running | finished | stopped | failed
        self._started_at: float | None = None
        self._elapsed = 0.0

    # ------------------------------------------------------------------ killable
    def request_stop(self, reason: str = "") -> None:
        """Запрос штатной остановки (кооперативно: нода сама выходит между квантами)."""
        with self._lock:
            self._stop_reason = reason
        self._stop_event.set()

    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    def _check_stop(self) -> None:
        if self.should_stop():
            self._status = "stopped"
            raise ModuleStopped(self.name, self._stop_reason)

    # --------------------------------------------------------------- throttleable
    def pace(self) -> None:
        """Один квант работы. Между квантами можно вставлять паузы (снижение CPU/GPU)."""
        self._check_stop()
        if self.throttle_delay_seconds > 0:
            time.sleep(self.throttle_delay_seconds)
        self._check_stop()

    # ----------------------------------------------------------------- observable
    def observe(self, step: int, message: str = "") -> None:
        """Зафиксировать прогресс текущего шага (для статус-бара и логов)."""
        with self._lock:
            self._step = step
            self._message = message

    def progress(self) -> Progress:
        """Текущий прогресс модуля: статус, шаг, прошедшее время, ETA."""
        with self._lock:
            running = self._status == "running"
            started = self._started_at
            step = self._step
            status = self._status
            message = self._message
            elapsed_fixed = self._elapsed
        if running and started is not None:
            elapsed = time.monotonic() - started
        else:
            elapsed = elapsed_fixed
        eta = None
        if running and step > 0 and self.total_steps > 0:
            eta = elapsed / step * (self.total_steps - step)
        return Progress(
            status=status,
            step=step,
            total_steps=self.total_steps,
            message=message,
            elapsed_seconds=elapsed,
            eta_seconds=eta,
        )

    # --------------------------------------------------------------- predictable
    def predict(self, data: DataObject) -> float:
        """Точная оценка времени работы по поданным данным (лекция 4:44).

        Предсказуемость: «по поданным на модуль данным можно точно оценить время
        работы от начала до конца — на каждый модуль можно поставить progress bar,
        и он будет показывать точно время». Базовая оценка — по объёму входа и
        total_steps; тяжёлые ноды обязаны переопределить. Это контрактная оценка
        до запуска, а не экстраполяция после старта (та остаётся в progress().eta).
        """
        volume = max(len(data.chunks), len(data.documents), len(data.tasks), 1)
        return volume * self.total_steps * self.throttle_delay_seconds

    # -------------------------------------------------- semantically identifiable
    # name и description обязательны и проверяются в __init_subclass__.

    @abc.abstractmethod
    def execute(self, data: DataObject) -> DataObject:
        """Бизнес-логика ноды. В заглушках возвращает объект данных без изменений."""

    # ---------------------------------------------------------- шаблон запуска
    def run(self, data: DataObject) -> DataObject:
        """Точка входа ноды графа: наблюдаемость + штатная остановка вокруг execute().

        Вызов мимо графа (вне шага LangGraph) запрещён конституцией п.11:
        событие стражу «ничего вне графа» и жёсткий возврат исполнения в граф —
        нода исполняется одноузловым подграфом LangGraph.
        """
        if not graph_context.is_inside_graph():
            from core.graph_runtime import force_into_graph

            return force_into_graph(self, data, via="run")
        with _ACTIVE_LOCK:
            _ACTIVE_MODULES.add(self)
        self._started_at = time.monotonic()
        self._status = "running"
        self._step = 0
        self._message = ""
        try:
            result = self.execute(data)
        except ModuleStopped:
            self._status = "stopped"
            data.status = "stopped"
            raise
        except Exception as exc:  # noqa: BLE001 - фиксируем сбой в объекте данных
            self._status = "failed"
            data.errors.append(f"{self.name}: {type(exc).__name__}: {exc}")
            raise
        else:
            self._status = "finished"
            result.trace.append(self.name)
            return result
        finally:
            self._elapsed = time.monotonic() - self._started_at
            with _ACTIVE_LOCK:
                _ACTIVE_MODULES.discard(self)
