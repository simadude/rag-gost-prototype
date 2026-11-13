"""Сопоставление кандидатов поиска с целевыми нормативами проверки.

Пользователь задаёт перечень целевых ГОСТ/СТО (request.target_gosts, контракт
`CheckRequest`); каналы поиска ограничивают кандидатов только документами из
перечня. Пустой перечень = проверка по всему корпусу.
"""
from __future__ import annotations


def hit_in_targets(hit: dict, targets: list[str]) -> bool:
    """Кандидат поиска принадлежит целевому документу (подстрока, без регистра)."""
    if not targets:
        return True
    haystack = " ".join(
        str(hit.get(key, "")) for key in ("source", "name", "section", "gost")
    ).lower()
    return any(str(target).lower() in haystack for target in targets)


def doc_prefixes(candidates: list[dict], targets: list[str]) -> set[str]:
    """Префиксы документов (`doc-XXXX`) кандидатов, попавших в целевые нормативы."""
    prefixes: set[str] = set()
    for candidate in candidates:
        if hit_in_targets(candidate, targets):
            prefixes.add(str(candidate.get("id", "")).split("#")[0])
    return prefixes


def fact_in_docs(fact: dict, prefixes: set[str]) -> bool:
    """Факт из базы знаний относится к документу из перечня префиксов."""
    if not prefixes:
        return False
    return str(fact.get("chunk_id", "")).split("#")[0] in prefixes
