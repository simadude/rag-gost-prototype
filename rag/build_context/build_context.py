"""Нода build_context: формирует пары «пункт ГОСТ + фрагмент решения» для передачи агентам проверки..

Источник в декомпозиции: B4 Сборка контекста. Контракт — docs/module-standard.md.
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port


class BuildContext(BaseModule):
    """Формирует пары «пункт ГОСТ + фрагмент решения» для передачи агентам проверки."""

    name = "build_context"
    description = "Формирует пары «пункт ГОСТ + фрагмент решения» для передачи агентам проверки"
    total_steps = 2

    def execute(self, data: DataObject) -> DataObject:
        """Связывает кандидатуры ГОСТ с чанками решения, по которым они найдены.

        retrieve_fragments помечает каждого кандидата полем solution_chunk_id —
        здесь по нему восстанавливается пара. Кандидаты без привязки (например,
        из дословного канала) остаются без фрагмента — агент проверки ответит
        needs_review. На холостом прогоне кандидатов нет — объект не меняется.
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, "шаг {} из {}: сборка пар контекста".format(step, self.total_steps))
            self.pace()
        if data.candidate_requirements:
            # Источник пар — отбор реранкера; без него (простые прогоны) — все кандидаты.
            selected = data.selected_requirements or data.candidate_requirements
            by_chunk = {
                str(chunk.get("id", "")): chunk for chunk in data.chunks
            }
            data.context_pairs = [
                (
                    candidate,
                    by_chunk.get(str(candidate.get("solution_chunk_id", ""))),
                )
                for candidate in selected
            ]
            validate_port("context_pairs", data.context_pairs)
        return data
