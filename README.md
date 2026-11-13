# ГОСТ-проверка: RAG-ассистент соответствия стандартам

Прототип системы, проверяющий документ (отчёт, решение) на соответствие нормативным документам (ГОСТ / СТО). Исполнение целиком живёт в графе [LangGraph](https://langchain-ai.github.io/langgraph/): 25 нод, три канала поиска (векторный / дословный / графовый по фактам), стражи на событиях графа, агентный слой проверки с вердиктами «статус / цитата / комментарий».

**Работает полностью офлайн, из коробки, без API-ключей** — все внешние службы (эмбеддер, LM-агенты, реранкер) подключаются через коннекторы и по умолчанию заменены детерминированными заглушками.

## Быстрый старт (офлайн)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 1. Индексация демо-корпуса через граф (заглушки: без сети и без GPU)
RAG_EMBEDDER=stub RAG_LM_PROVIDER=stub \
  .venv/bin/python rag/run_index.py --source rag/tests/data/corpus/

# 2. Проверка демо-решения через маршрут check → Markdown-отчёт
RAG_EMBEDDER=stub RAG_LM_PROVIDER=stub \
  .venv/bin/python rag/run_check_demo.py rag/tests/data/solution-demo.txt

# 3. Батарея тестов (31 проверка: модули → умения → маршруты графа)
.venv/bin/python rag/run_tests.py

# Доказательство «ничего вне LangGraph» (5 линий: AST, Pregel, стражи)
.venv/bin/python rag/prove_langgraph.py
```

Отчёт проверки появится в `rag/var/reports/report-<имя_прогона>.md`.

## Что внутри

```
rag/
├── core/          — граф исполнения: DataObject (порт-контракт), сборка 25 нод,
│                    стражи по событиям (ничего вне графа, отличимость), runtime
├── providers/     — коннекторы внешнего контура: векторная БД (SQLite WAL /
│                    PostgreSQL), база знаний, эмбеддер, LM-провайдер, реранкер
├── <нода>/        — 25 нод-модулей (index-конвейер, поиск, агенты проверки, отчёт)
├── run_index.py   — CLI индексации (маршрут index)
├── run_check_demo.py — CLI проверки документа (маршрут check) → отчёт
├── run_tests.py   — трёхуровневое тестирование (31/31)
├── prove_langgraph.py — протокол доказательства исполнения в графе
├── smoke_*.py     — смоуки стражей, изоляции графа, провайдеров
└── tests/data/    — демо-корпус (7 документов) + демо-решение
docs/               — конституция (принципы), карта нод, регламент тестирования,
                      схема графа (Mermaid/PNG), отчёты о тестированиях
```

## Как включить «настоящую» начинку

Все внешние службы переключаются переменными окружения — ноды не меняются
(критерий коннекторов: смена бэкенда «щелчком»).

| Служба | Переменные | По умолчанию |
|---|---|---|
| Векторная БД | `RAG_VECTOR_DB=sqlite`, `RAG_SQLITE_PATH=…` | `sqlite` (WAL) |
| База знаний | `RAG_KNOWLEDGE_DB=sqlite`, `RAG_KNOWLEDGE_PATH=…` | `sqlite` |
| Эмбеддер | `RAG_EMBEDDER=llamacpp`, `RAG_EMBEDDER_URL=http://127.0.0.1:8912` | `stub` |
| LM-провайдер (агенты) | `RAG_LM_PROVIDER=openrouter`, `RAG_LM_MODEL=…`, `RAG_LM_API_KEY=…` | `stub` |
| Реранкер | `RAG_RERANKER=llamacpp`, `RAG_RERANKER_URL=http://127.0.0.1:8915` | `stub` |

Эмбеддер и реранкер — локальные модели через
[llama.cpp](https://github.com/ggml-org/llama.cpp) `llama-server`:

```bash
llama-server -m Qwen3-Embedding-4B-Q8_0.gguf --embedding --port 8912 -c 32768 -ngl 99
llama-server -m Qwen3-Reranker-4B.Q8_0.rerank.gguf --reranking --port 8915 -c 8192 -ngl 99
```

Для Qwen3-Reranker GGUF должен содержать классификационную голову (`cls.output.weight`), метки классов и rerank-шаблон — см. рецепт `conversion/qwen.py` в поставке llama.cpp. LM-агенты работают с любым OpenAI-совместимым API (ключ передавайте переменной окружения — в репозитории ключей нет). Разбор PDF требует `pdftotext` (poppler-utils); DOCX — stdlib.

## Пример: проверка реального отчёта

```bash
RAG_VECTOR_DB=sqlite RAG_SQLITE_PATH=rag/var/vectors.db \
RAG_KNOWLEDGE_DB=sqlite RAG_KNOWLEDGE_PATH=rag/var/knowledge.db \
RAG_EMBEDDER=llamacpp RAG_EMBEDDER_URL=http://127.0.0.1:8912 \
RAG_RERANKER=llamacpp RAG_RERANKER_URL=http://127.0.0.1:8915 \
RAG_LM_PROVIDER=openrouter RAG_LM_MODEL=z-ai/glm-5.3-flash RAG_LM_API_KEY=… \
RAG_RETRIEVE_TOP_K=50 RAG_RERANK_TOP_K=3 \
  .venv/bin/python rag/run_check_demo.py <решение.pdf> \
  --target <подстрока имени целевого СТО/ГОСТа> --run-id my-check
```

Фильтр `--target` ограничивает проверку выбранными нормативами; у каждого чанка решения реранкер отбирает свои ближайшие пункты, агент проверки возвращает вердикт с дословной цитатой (цитаты, которых нет во фрагменте, бракуются — анти-галлюцинация).

## Документация

- `docs/constitution.md` — принципы системы (исполнение только в графе, порты, отличимость);
- `docs/node-map.md` — карта 25 нод, маршруты check/index/refresh/status, ходки к провайдерам;
- `docs/testing.md` + `docs/testing-report.md` — регламент и сводные результаты;
- `docs/diagram.png` / `docs/diagram.mmd` — схема графа.

## Статус прототипа

Работает: индексация с извлечением фактов, три канала поиска, реранкинг, агентная проверка с вердиктами и цитатами, Markdown-отчёты, полный тестовый контур. Каркасные заглушки: `measure_quality` (нужна эталонная разметка), `handle_followup` (нужен интерактив), разрешение конфликтов вердиктов, PDF-рендер отчёта.
