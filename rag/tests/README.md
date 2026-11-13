# Тестовые данные системы

> Карта входов/выходов всех тестов. Регламент — `docs/testing.md`,
> сводный отчёт — `docs/testing-report.md`.
> Правило (решение 12.11): **все тестовые файлы — внутри проекта**, никаких
> разбросанных входов в /tmp или домашней папке.

## Входы — всё в `rag/tests/data/`

| Что | Где |
|---|---|
| **Корпус индексации** (реальные документы, 7 файлов, ~4 МБ) | `rag/tests/data/corpus/` |
| — СТО СК-СТО-ТР-04-1.005-2015 (правила оформления отчётов ВВГУ) | `corpus/sto-rules.pdf` |
| — СТО Оформление письменных работ | `corpus/СТО Оформление письменных работ.pdf` |
| — документы учебной практики (аннотация, РПД, отчёт, работа студента) | остальные 5 файлов `corpus/` |
| Демо-решение для маршрута `check` (синтетика с намеренными нарушениями: прямые кавычки → P 02-06, дефис вместо тире → P 02-07) | `rag/tests/data/solution-demo.txt` |
| Синтетические фрагменты бенчмарка эмбеддеров (18 фрагментов, дистракторы d13–d18) | внутри `rag/test_embedder_quality.py` |

Реальные ГОСТы (не СТО) на входе ещё ни разу не прогонялись — новый документ
кладётся в `corpus/` и индексируется той же командой.

## Выходы — всё в `rag/var/`

| Что | Где |
|---|---|
| Векторы корпуса | `rag/var/vectors.db` (SQLite WAL, 242 чанка, Qwen3-4B dim=2560) |
| Факты и связи (база знаний) | `rag/var/knowledge.db` (~2200 фактов) |
| Кэш фактов (переиндексация без расхода LM) | `rag/var/facts_cache.json` |
| Отчёты проверок (Markdown) | `rag/var/reports/report-<run_id>.md` |
| БД бенчмарков эмбеддеров | `rag/var/vectors-sto.db`, `vectors-test.db` |
| Бэкапы БД прошлых циклов | `rag/var/*.bak-*` |

## Команды

```bash
cd <корень репозитория>  # папка с rag/ и README

# Батарея (без сети): регрессия 31/31, доказательство графа, стражи, провайдеры
.venv/bin/python rag/run_tests.py
.venv/bin/python rag/prove_langgraph.py
.venv/bin/python rag/run_skeleton.py
.venv/bin/python rag/smoke_guards.py
.venv/bin/python rag/smoke_nothing_outside_graph.py
.venv/bin/python rag/smoke_providers.py

# Сквозные прогоны (нужны службы: эмбеддер 8912, реранкер 8915; LM — OpenRouter,
# переменные — см. шапки docs/research/rerankers.md и docs/research/lm-providers.md)
RAG_VECTOR_DB=sqlite RAG_SQLITE_PATH=rag/var/vectors.db \
RAG_KNOWLEDGE_DB=sqlite RAG_KNOWLEDGE_PATH=rag/var/knowledge.db \
RAG_EMBEDDER=llamacpp RAG_EMBEDDER_URL=http://127.0.0.1:8912 \
RAG_RERANKER=llamacpp RAG_RERANKER_URL=http://127.0.0.1:8915 \
RAG_LM_PROVIDER=openrouter RAG_LM_MODEL=z-ai/glm-5.3-flash \
.venv/bin/python rag/run_index.py --source rag/tests/data/corpus/

.venv/bin/python rag/run_check_demo.py rag/tests/data/solution-demo.txt --target sto-rules

# Качественные бенчмарки эмбеддеров (службы 8912/8913/8914)
.venv/bin/python rag/test_embedder_quality.py
.venv/bin/python rag/test_real_corpus.py --db rag/var/vectors-sto.db
```
