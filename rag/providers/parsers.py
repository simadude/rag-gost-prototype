"""Коннектор разбора документов (B1, TASKS-3: «не выбрасывать разметку»).

Тяжёлое — за внешним контуром: PDF разбирает системная утилита poppler
(`pdftotext`, путь — RAG_PDFTOTEXT; замена утилиты — смена коннектора, ноды
не знают деталей). DOCX/TXT/MD — чистый stdlib. Структура сохраняется:
- PDF: постранично (\f → страницы), текст как есть;
- DOCX: абзацы по порядку; таблицы разворачиваются в строки «a | b | c»
  (таблицы ГОСТ-документов нельзя терять); разбивка на страницы в docx
  не хранится — pages пустой (честно фиксируем в метаданных);
- TXT/MD: целиком одной «страницей».

Формат результата: {"kind": "pdf|docx|txt|md", "pages": [{"page": int|None, "text": str}]}
"""
from __future__ import annotations

import os
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def parse_pdf(path: Path) -> list[dict]:
    """PDF → страницы (poppler pdftotext, UTF-8, \f — разделитель страниц)."""
    tool = os.environ.get("RAG_PDFTOTEXT", "pdftotext")
    result = subprocess.run(
        [tool, "-enc", "UTF-8", str(path), "-"],
        capture_output=True, timeout=120, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext не смог разобрать {path.name}: {result.stderr[:200]!r}")
    pages = []
    for number, page_text in enumerate(result.stdout.decode("utf-8").split("\f"), start=1):
        stripped = page_text.strip("\n")
        if stripped:
            pages.append({"page": number, "text": stripped})
    return pages


def parse_docx(path: Path) -> list[dict]:
    """DOCX → абзацы по порядку, таблицы в строки «a | b | c» (структуру сохраняем)."""
    text_parts: list[str] = []
    with zipfile.ZipFile(path) as docx:
        with docx.open("word/document.xml") as xml_file:
            body = ElementTree.parse(xml_file).getroot().find(f"{_W}body")
    if body is None:
        raise RuntimeError(f"в {path.name} нет word/document.xml с телом документа")
    for element in body:
        if element.tag == f"{_W}p":
            line = "".join(node.text or "" for node in element.iter(f"{_W}t"))
            if line.strip():
                text_parts.append(line)
        elif element.tag == f"{_W}tbl":
            for row in element.findall(f"{_W}tr"):
                cells = []
                for cell in row.findall(f"{_W}tc"):
                    cell_text = " ".join(
                        "".join(node.text or "" for node in p.iter(f"{_W}t")).strip()
                        for p in cell.findall(f"{_W}p")
                    ).strip()
                    cells.append(cell_text)
                if any(cells):
                    text_parts.append(" | ".join(cells))
    # docx страниц не хранит — честный пустой список страниц
    if text_parts:
        return [{"page": None, "text": "\n".join(text_parts)}]
    return []


def parse_plain(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [{"page": None, "text": text}] if text.strip() else []


SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


def parse_document_file(path: Path) -> dict:
    """Разбор одного файла коннектором по расширению."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return {"kind": "pdf", "pages": parse_pdf(path)}
    if suffix == ".docx":
        return {"kind": "docx", "pages": parse_docx(path)}
    if suffix in (".txt", ".md"):
        return {"kind": suffix.lstrip("."), "pages": parse_plain(path)}
    raise ValueError(f"Формат {suffix!r} не поддерживается коннектором разбора")
