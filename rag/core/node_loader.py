"""Загрузчик ноды по имени: нода — отдельный исполняемый фрагмент (пакет).

Конституция, п.2: каждая нода — отдельный исполняемый фрагмент кода в отдельной
папке, названной именем узла. Загрузчик позволяет исполнить ноду без сборки
всего графа — этим пользуется и изоляция процесса (`process_runner`), и подграфы-
умения (`skill`).
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))


def node_class_name(name: str) -> str:
    """snake_case имя папки → имя класса: store_vectors → StoreVectors."""
    return "".join(part.capitalize() for part in name.split("_"))


def load_node_class(name: str):
    """Импортирует класс ноды из её пакета: project/<имя>/<имя>.py."""
    package = importlib.import_module(f"{name}.{name}")
    cls = getattr(package, node_class_name(name), None)
    if cls is None:
        raise AttributeError(f"В пакете {name} нет класса {node_class_name(name)}")
    return cls


def list_node_names() -> list[str]:
    """Все ноды системы: папки project/ с файлом <имя>/<имя>.py (без core)."""
    names = []
    for child in sorted(_PROJECT_DIR.iterdir()):
        if child.is_dir() and (child / f"{child.name}.py").is_file():
            names.append(child.name)
    return names
