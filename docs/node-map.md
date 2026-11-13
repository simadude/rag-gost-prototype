# Карта нод графа исполнения (Задача 1 + слой поиска + встреча 2)

> Система: RAG-ассистент проверки технических решений на соответствие ГОСТу.
> Это карта **графа исполнения** (оркестрация модулей), не графа построения ТЗ
> и не графа знаний (TASKS.md, правило 7).
> Источник имён: `project/core/data_object.py` — каждое поле объекта данных
> заполняет строго одна нода, поэтому список нод зафиксирован там же.
> Гранулярность: 25 нод (24 конвейерных + узел системы самознания; ориентир
> TASKS.md — 20–25).
>
> Встреча 2 (TASKS-2): внешний контур и провайдеры (A4), умение-подграф (A3),
> стражи по событиям (B1), система самознания (B2), схема — Mermaid (A5).

## Входы системы (разделены по решению от 22.10)

- **ГОСТ и СТО — внутренний вход системы**: тексты поступают в ветку
  `index`/`refresh` и никогда не приходят от пользователя.
- **Документ-решение и запрос — вход от пользователя**: подаются через
  `user_interface` в ветке `check` и проверяются на каждом шаге конвейера.

## Внешний контур и провайдеры (A4, лекция 11:10–21:30)

База данных — не труба и не волшебная палочка: в неё *ходят* и от неё
*получают ответы*, **сквозь неё ничего не течёт**. БД и хранилище знаний —
разные вещи, и ходки к ним разные. За внешним контуром — четыре
службы-провайдера, доступ только через коннекторы (`project/providers/`):

| Провайдер | Услуга | Коннектор (фабрика) | Переключение |
|---|---|---|---|
| SQL-БД векторов | векторы + чанки; векторный и дословный каналы поиска | `providers.stores.get_vector_store()` | `RAG_VECTOR_DB`: `memory` / `sqlite` (WAL) / `postgres` |
| База знаний | факты и связи; графовый канал поиска | `providers.stores.get_knowledge_base()` | `RAG_KNOWLEDGE_DB`: `memory` / `sqlite` |
| Эмбеддер-служба | векторное представление текста (Qwen3 Embedding — тяжёлое, за контуром); **входные ворота (B1)**: `limits()` — лимит длины входа модели; локальная модель — `project/serve_embedder.py` | `providers.embedder.get_embedder()` | `RAG_EMBEDDER`: `stub` / `http` (+`RAG_EMBEDDER_URL`) |
| LM-провайдер | API-узел агентов (все агенты ходят только сюда) | `providers.lm_provider.get_lm_provider()` | `RAG_LM_PROVIDER`: `stub` / `http` (+`RAG_LM_URL`) |

Критерий коннекторов: замена SQLite → PostgreSQL «делается щелчком пальцев» —
сменой `RAG_VECTOR_DB`, ноды не трогаются (smoke: `project/smoke_providers.py`).
SQLite остаётся, включён WAL («разносит во времени несчастных пользователей»);
PostgreSQL — только когда будет ~миллион запросов в секунду.

## Связь с декомпозицией (`rag_system_decomposition.json`)

| Подсистема декомпозиции | Компоненты | Ноды графа исполнения |
|---|---|---|
| 1. Конвейер индексации (офлайн) | A1–A5 | collect_sources, parse_document, chunk_text, embed_chunks, store_vectors |
| Графовый слой индексации (новый) | — | extract_facts, store_facts |
| 2. Контур проверки (онлайн) | B1–B4 | user_interface, retrieve_fragments (векторный), literal_search (дословный), graph_search (факты/связи), rerank_fragments, build_context |
| 3. Агентный слой проверки | C1–C4 | distribute_tasks, verify_requirement, format_verdict, aggregate_verdicts |
| 4. Отчётность | D1–D3 | compose_report, render_report, handle_followup |
| 5. Инфраструктура | E1–E4 | schedule_checks, enforce_security, refresh_corpus, measure_quality |
| 6. Самознание (встреча 2) | — | system_self_awareness |

Компонент A1 «Корпус документов» — это данные (папка источников), а не нода;
его обработку выполняет нода `collect_sources`. Компонент A5 «Векторная БД» —
это провайдер SQL-БД за внешним контуром; работа с ней оформлена нодой
`store_vectors` через коннектор.

## Почему три канала поиска

Векторный поиск хорошо находит смысловые фрагменты, но плохо работает на
документах с большим количеством чисел (таблицы параметров, нормативные
значения). Поэтому поиск опирается на три канала, которые затем объединяются
и переранкингуются единым механизмом:

1. **Векторный** — `retrieve_fragments`: семантическая близость.
2. **Дословный** — `literal_search`: точные совпадения текста и чисел.
3. **Графовый** — `graph_search`: факты и связи между ними из базы знаний
   (факты собирает агент `extract_facts` → `store_facts` на этапе индексации).

## Список нод (25)

| № | Нода (имя папки) | Агент? | Назначение | Входы (DataObject) | Выходы (DataObject) |
|---|---|---|---|---|---|
| 1 | `user_interface` | нет | Принимает запрос пользователя: PDF решения + целевые ГОСТы, выбирает маршрут прогона (check / index / refresh / status), показывает отчёт | запрос пользователя | `request`, `mode`; из отчёта — `presentation`, `followup_question` |
| 2 | `enforce_security` | нет | Проверяет права доступа и локальность данных: корпоративные СТО не покидают контур (E3) | `request` | `request` (или `status="rejected"`) |
| 3 | `schedule_checks` | нет | Ставит задание на проверку в очередь, распределяет лимиты LLM API (E1) | `request` | `request` |
| 4 | `collect_sources` | нет | Собирает файлы корпуса (ГОСТы + СТО) из папки источников (A1) | список источников | `source_files` |
| 5 | `refresh_corpus` | нет | Отслеживает новые редакции ГОСТов и решает, что переиндексировать (E2) | сведения об обновлениях | `source_files` |
| 6 | `parse_document` | нет | Извлекает текст, таблицы и схемы из PDF с привязкой к страницам (A2; переиспользуется для решения пользователя) | `source_files` или файл решения | `documents` |
| 7 | `chunk_text` | нет | Режет документы на чанки по пунктам/разделам, добавляет метаданные (№ ГОСТа, пункт, редакция) (A3) | `documents` | `chunks` |
| 8 | `embed_chunks` | нет (модель за контуром) | Кодирует чанки в векторы **через коннектор эмбеддер-службы** (Qwen3); единая модель для базы и запросов (A4); **входные ворота (B1)**: режет чанки под лимит модели, отчёт в `embedder_cuts` | `chunks` | `vectors`, `embedder_cuts` |
| 9 | `store_vectors` | нет | Записывает векторы + метаданные **через коннектор SQL-БД** | `vectors` | `stored_count` |
| 10 | `extract_facts` | **да** | Агент фактов: извлекает из чанков ГОСТа числа, ограничения, утверждения — **через коннектор LM-провайдера** | `chunks` | `facts` |
| 11 | `store_facts` | нет | Упаковывает факты и связи **через коннектор базы знаний** | `facts` | `facts_stored` |
| 12 | `retrieve_fragments` | нет | Векторный канал: top-K релевантных пунктов ГОСТа — ходка к SQL-БД за ответом | `chunks` решения | `candidate_requirements` |
| 13 | `literal_search` | нет | Дословный канал: точные совпадения текста и чисел — ходка к SQL-БД за ответом | `chunks` решения | `literal_hits` |
| 14 | `graph_search` | нет | Графовый канал: связанные факты — ходка к базе знаний за ответом | `chunks` решения | `graph_candidates` |
| 15 | `rerank_fragments` | полу-агент | Объединяет кандидатов трёх каналов, снимает дубли и пересортировывает (в зрелой системе — LLM-реранк) | `candidate_requirements` + `literal_hits` + `graph_candidates` | `selected_requirements` |
| 16 | `build_context` | нет | Формирует пары «пункт ГОСТ + фрагмент решения» для агентов | `selected_requirements` + `chunks` | `context_pairs` |
| 17 | `distribute_tasks` | нет | Разбивает контекст на задачи по пунктам (1 пункт = 1 задача) | `context_pairs` | `tasks` |
| 18 | `verify_requirement` | **да** | Агент проверки: сравнивает один пункт ГОСТа с фрагментом решения через LLM (коннектор LM-провайдера) | `tasks` | `raw_answers` |
| 19 | `format_verdict` | нет | Приводит ответы к схеме вердикта: статус / цитата / исправление | `raw_answers` | `verdicts` |
| 20 | `aggregate_verdicts` | **да** (при конфликтах) | Собирает вердикты, снимает конфликты, формирует сводный статус документа | `verdicts` | `summary_verdict` |
| 21 | `compose_report` | нет | Собирает итоговый отчёт: пункт ГОСТ / фрагмент / статус / рекомендация | `summary_verdict` | `report` |
| 22 | `render_report` | нет | Готовит показ отчёта: подсветка нарушений, экспорт PDF/MD | `report` | `presentation` |
| 23 | `handle_followup` | **да** | Обрабатывает уточнение пользователя (интент) и возвращает прогон к `user_interface` | `followup_question` | возврат к `user_interface` |
| 24 | `measure_quality` | нет | Считает метрики качества проверки | `report` | `metrics` |
| 25 | `system_self_awareness` | агент по вопросу | **Система самознания (B2)**: сообщает состояние системы и отвечает, умеет ли она запрошенное, переиспользуя поисковый контур (дословный канал по реестру нод и умений) | `followup_question` (вопрос) или справочный режим | `capabilities_report` |

Где именно возникает когнитивная деятельность — `docs/agents-map.md` (A1).

## Топология графа (маршруты)

- **check** (основной): `user_interface → enforce_security → schedule_checks →
  parse_document → chunk_text → retrieve_fragments → literal_search →
  graph_search → rerank_fragments → build_context → distribute_tasks →
  verify_requirement → format_verdict → aggregate_verdicts → compose_report →
  render_report → handle_followup → measure_quality → END`
- **index** (офлайн): `user_interface → collect_sources → parse_document →
  chunk_text → embed_chunks → store_vectors → extract_facts → store_facts → END`
  — целиком сворачивается в умение `prepare_knowledge_base` (подграф,
  `docs/skills-registry.md`; запуск отдельно: `python3 project/run_skill.py
  prepare_knowledge_base`).
- **refresh**: `user_interface → refresh_corpus → collect_sources → …(как index)`
- **status** (встреча 2): `user_interface → system_self_awareness → END` —
  вопрос «что у системы происходит / что она умеет».
- **Цикл уточнений**: если `handle_followup` получает вопрос пользователя —
  возврат к `user_interface` (иначе — к `measure_quality`).
- **Отклонение**: если `enforce_security` не пропускает запрос — `END` со
  `status="rejected"`.
- **Ходки к провайдерам** (пунктир на схеме): `embed_chunks → эмбеддер-служба`,
  `store_vectors → SQL-БД`, `store_facts → база знаний` (запись);
  `retrieve_fragments`/`literal_search → SQL-БД`, `graph_search → база знаний`
  (чтение); `extract_facts`, `verify_requirement`, `aggregate_verdicts` (при
  конфликте), `handle_followup` → LM-провайдер (агенты). Сквозь БД ничего
  не течёт — это ходки «за ответом», не потоки.
- **На схеме** (`docs/diagram.mmd` — единственный источник, `diagram.png` —
  производная) офлайн-ветка изображена без отдельного END: её завершение —
  ходки «запись векторов»/«запись фактов» к провайдерам, чтобы не читалось
  как тупик. Финальный END в коде графа остаётся: техническая точка
  завершения прогона LangGraph.

## Стражи (B1, встреча 2)

Стражи — специальные модули, живущие **на самом графе** и запускающиеся
**методом самого графа по событиям** `node_added` / `node_changed`
(не по таймеру): `core/guards.py`. При сборке графа каждая нода эмитит
`node_added`; простой страж `guard_self_description` проверяет каскад
самоописанности (≤10 символов — fail; <30 — ниже контракта; 30–200 — ok;
>200 — интеллектуальный страж-агент через LM-провайдера). Отчёт стражей
печатается в `project/run_skeleton.py`; smoke — `project/smoke_guards.py`.

## Запуск и проверки

- Холостой прогон (4 маршрута + отчёт стражей): `python3 project/run_skeleton.py`
  — `trace` маршрута `check` покрывает 18 нод основного конвейера проверки.
- Изолированный запуск ноды + жёсткая остановка:
  `python3 project/run_node.py measure_quality --kill-after 0.2`.
- Запуск умения отдельно: `python3 project/run_skill.py prepare_knowledge_base`.
- Провайдеры: `python3 project/smoke_providers.py`; стражи: `python3 project/smoke_guards.py`.

До первого прохода система не имела исполняемых модулей — все ноды
реализуются как каркасные заглушки, топология выше — эталон для сборки графа.
