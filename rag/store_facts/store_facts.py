"""Нода store_facts: упаковывает факты вместе со связями между ними в графовую базу знаний.

Источник в декомпозиции: Слой графового поиска (индексация). Контракт — docs/module-standard.md.
A4 (лекция 11:10–13:10): база данных и хранилище знаний — **разные вещи**, и способы
ходить к ним разные. К базе знаний — свой коннектор `providers.stores.get_knowledge_base()`;
сквозь неё ничего не течёт — в неё ходят за записью фактов и связей.
"""
from __future__ import annotations

from core.base_module import BaseModule
from core.data_object import DataObject, validate_port
from providers.stores import get_knowledge_base


class StoreFacts(BaseModule):
    """Упаковывает факты вместе со связями между ними в графовую базу знаний."""

    name = "store_facts"
    description = "Упаковывает факты вместе со связями между ними в графовую базу знаний."
    total_steps = 2

    def execute(self, data: DataObject) -> DataObject:
        """Пишет факты и связи через коннектор провайдера базы знаний.

        На холостом прогоне фактов нет — объект данных не меняется;
        на реальном прогоне `facts_stored` = сколько фактов легло в базу.
        """
        for step in range(1, self.total_steps + 1):
            self.observe(step, "заглушка: шаг {} из {}".format(step, self.total_steps))
            self.pace()
        if data.facts:
            kb = get_knowledge_base()
            for i, fact in enumerate(data.facts):
                kb.add_fact(fact)
                if i:
                    kb.link(str(data.facts[i - 1]["id"]), str(fact["id"]), "следующий")
            data.facts_stored = len(data.facts)
            validate_port("facts_stored", data.facts_stored)
        return data
