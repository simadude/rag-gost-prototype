"""Тесты качества эмбеддеров на русском корпусе (B1, план — docs/research/embedders.md §4).

    python3 project/test_embedder_quality.py            # обе настроенные службы
    python3 project/test_embedder_quality.py --url http://127.0.0.1:8912

Мини-корпус: ГОСТ/СТО-подобные фрагменты (числа, марки сталей, сварка, испытания).
Метрики: hit@1/3/5 (попал ли целевой фрагмент в top-k), MRR, время на запрос.
Промпт-шаблоны — по картам моделей:
- Qwen3-Embedding: запрос с инструкцией ("Instruct: …\nQuery: …"), документы как есть;
- EmbeddingGemma: документы "title: none | text: …", запрос "task: search result | query: …".
Транспорт — тот же коннектор, что у нод (providers.embedder.LlamaCppEmbedder).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from providers.embedder import LlamaCppEmbedder  # noqa: E402

INSTRUCTION_QWEN = ("Given a search query, retrieve relevant clauses of Russian technical "
                    "standards (GOST/STO) and engineering requirements that answer the query")

# --- мини-корпус: (id, текст). Целевой фрагмент для каждого запроса — по индексу.
DOCS: list[tuple[str, str]] = [
    ("d1", "Толщина стенки корпуса должна быть не менее 4 мм. Допуск по толщине стенки — ±0,3 мм."),
    ("d2", "Марка стали для корпуса аппарата — 09Г2С; допускается замена на сталь 09Г2С-12 по ГОСТ 19281."),
    ("d3", "Сварные швы класса Т3 контролировать ультразвуковым методом по ГОСТ 14782, объём контроля — не менее 25 % длины швов."),
    ("d4", "Испытания аппарата проводить гидравлическим давлением 1,6 МПа в течение 10 минут; падение давления не допускается."),
    ("d5", "Маркировка аппарата наносится на табличку по ГОСТ 3242: товарный знак изготовителя, номер аппарата, год выпуска."),
    ("d6", "Межцентровое расстояние отверстий под болты М12 — 80±0,2 мм; отверстия выполняются под болты по ГОСТ 7798."),
    ("d7", "Покрытие наружных поверхностей — эмаль ПФ-115, два слоя по ГОСТ 6465; толщина покрытия 40–60 мкм."),
    ("d8", "Зазор между фланцем и прокладкой не должен превышать 0,5 мм; прокладка — паронит ПОН-Б по ГОСТ 481."),
    ("d9", "Твёрдость поверхности после цементации — 56–62 HRC; глубина цементации 0,8–1,2 мм."),
    ("d10", "Резьба шпилек — М16×2-6g; гайки — класса прочности 8 по ГОСТ 5915."),
    ("d11", "Овальность и конусность цилиндрических поверхностей — не более 0,05 мм на длине 100 мм."),
    ("d12", "Расчётный срок службы аппарата — не менее 15 лет; межремонтный период — 3 года."),
    ("d13", "Раздел 6. Контроль качества сварных соединений. " + ("Методика визуального и измерительного контроля изложена в разделе 5. " * 40)
            + "Радиографический метод контроля сварных швов — по ГОСТ 7512, чувствительность контроля — 2 класс по ГОСТ 14249."),
    ("d14", "Допускаемое отклонение формы опорных поверхностей — не более 0,1 мм на длине 1000 мм."),
    # --- дистракторы: тот же тип величины, другое значение (проверка на путаницу)
    ("d15", "Толщина накладного листа должна быть не менее 6 мм; допуск по толщине листа — ±0,5 мм."),
    ("d16", "Объём контроля сварных швов радиографическим методом — 100 % для швов класса Т1."),
    ("d17", "Гидравлические испытания трубопроводов проводить давлением 2,4 МПа с выдержкой 15 минут."),
    ("d18", "Толщина лакокрасочного покрытия внутренних поверхностей — 80–100 мкм, грунт ГФ-021."),
]

# --- запросы инженера: (id, текст, целевой doc id, набор)
QUERIES: list[tuple[str, str, str, str]] = [
    # набор easy: прямые формулировки
    ("q1", "какая минимальная толщина стенки корпуса и допуск?", "d1", "easy"),
    ("q2", "какая марка стали допускается для корпуса аппарата?", "d2", "easy"),
    ("q3", "каким методом и в каком объёме контролировать сварные швы?", "d3", "easy"),
    ("q4", "какое давление гидравлических испытаний и время выдержки?", "d4", "easy"),
    ("q5", "что должно быть указано на маркировочной табличке?", "d5", "easy"),
    ("q6", "какое межцентровое расстояние отверстий под болты М12?", "d6", "easy"),
    ("q7", "какое лакокрасочное покрытие наружных поверхностей и толщина?", "d7", "easy"),
    ("q8", "какая прокладка для фланца и допустимый зазор?", "d8", "easy"),
    ("q9", "радиографический контроль сварных швов — по какому ГОСТу и какая чувствительность?", "d13", "easy"),
    # набор hard: жаргон, аббревиатуры, непрямые формулировки, дистракторы
    ("h1", "УЗК швов Т3 — сколько процентов длины контролировать?", "d3", "hard"),
    ("h2", "опрессовка аппарата: какое давление и сколько держать?", "d4", "hard"),
    ("h3", "из какой стали делать обечайку?", "d2", "hard"),
    ("h4", "чем уплотнять разъём фланца?", "d8", "hard"),
    ("h5", "минимальная толщина листа обшивки и отклонение?", "d1", "hard"),
    ("h6", "какой объём рентгеновского контроля для швов первого класса?", "d16", "hard"),
    ("h7", "через сколько лет капремонт аппарата?", "d12", "hard"),
    ("h8", "грунтовка под внутреннее покрытие — какая и сколько мкм?", "d18", "hard"),
    # набор no-match: калибровка — релевантного фрагмента в корпусе нет
    ("n1", "какая температура плавления припоя ПОС-40?", "—", "no-match"),
]

SERVICES = {
    "qwen3-embedding-4b": {
        "url": "http://127.0.0.1:8912",
        "doc_prompt": "{t}",  # документы как есть (карта модели)
        "query_prompt": f"Instruct: {INSTRUCTION_QWEN}\nQuery: {{q}}",
    },
    "embeddinggemma-2": {
        "url": "http://127.0.0.1:8913",
        "doc_prompt": "title: none | text: {t}",       # шаблоны из руководства EmbeddingGemma
        "query_prompt": "task: search result | query: {q}",
    },
    "qwen3-embedding-4b-raw": {
        # A/B: та же служба 8912 без инструкции — замер вклада промпта из карты
        "url": "http://127.0.0.1:8912",
        "doc_prompt": "{t}",
        "query_prompt": "{q}",
    },
    "embeddinggemma-2-raw": {
        # A/B: Gemma без шаблонов руководства («title: none | text: …» и т.п.)
        "url": "http://127.0.0.1:8913",
        "doc_prompt": "{t}",
        "query_prompt": "{q}",
    },
    "qwen3-vl-embedding-2b": {
        "url": "http://127.0.0.1:8914",
        # ВАЖНО (замер 12.11.2026): сырой текст без префиксов. Инструкция-префикс
        # «Instruct: … Query: …» рушит качество (easy hit@1 0,11 → 0,89): модель
        # рассчитана на chat-шаблон с системной инструкцией, который llama-server
        # для /v1/embeddings не применяет, и префиксный текст попадает не туда.
        "doc_prompt": "{t}",
        "query_prompt": "{q}",
    },
}


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def service_alive(url: str) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=3) as response:
            return json.loads(response.read()).get("status") == "ok"
    except Exception:  # noqa: BLE001 - служба не поднята → пропускаем с сообщением
        return False


def evaluate(name: str, config: dict) -> dict:
    emb = LlamaCppEmbedder(url=config["url"])
    limits = emb.limits()
    docs = [config["doc_prompt"].format(t=t) for _, t in DOCS]
    assert all(len(t) <= limits.max_input_chars for t in docs), "длинный чанк превысил ворота"
    t0 = time.monotonic()
    doc_vectors = emb.embed(docs)
    index_seconds = time.monotonic() - t0

    per_set: dict[str, dict] = {}
    query_times = []
    rows = []
    for qid, qtext, target, qset in QUERIES:
        prompt = config["query_prompt"].format(q=qtext)
        t0 = time.monotonic()
        qvec = emb.embed([prompt])[0]
        query_times.append(time.monotonic() - t0)
        sims = sorted(
            ((cosine(qvec, dv), doc_id) for dv, (doc_id, _) in zip(doc_vectors, DOCS)),
            key=lambda pair: -pair[0],
        )
        if target == "—":  # no-match: калибровка — цель не должна сидеть высоко
            rows.append((qid, qset, target, "—", round(sims[0][0], 3), round(sims[0][0], 3)))
            per_set.setdefault(qset, {"hits": {1: 0, 3: 0, 5: 0}, "ranks": [], "rows": []})
            continue
        rank = next(i for i, (_, doc_id) in enumerate(sims, start=1) if doc_id == target)
        bucket = per_set.setdefault(qset, {"hits": {1: 0, 3: 0, 5: 0}, "ranks": [], "rows": []})
        for k in bucket["hits"]:
            bucket["hits"][k] += int(rank <= k)
        bucket["ranks"].append(rank)
        bucket["rows"].append((qid, target, rank, round(sims[0][0], 3), round(sims[rank - 1][0], 3)))
        rows.append((qid, qset, target, rank, round(sims[0][0], 3), round(sims[rank - 1][0], 3)))

    summary = {}
    for qset, bucket in per_set.items():
        n = len(bucket["ranks"])
        summary[qset] = {
            "n": n,
            "hit1": bucket["hits"][1] / n if n else 0.0,
            "hit3": bucket["hits"][3] / n if n else 0.0,
            "hit5": bucket["hits"][5] / n if n else 0.0,
            "mrr": (sum(1.0 / r for r in bucket["ranks"]) / n) if n else 0.0,
        }
    return {
        "name": name, "model": limits.model, "dim": limits.dim,
        "max_input_chars": limits.max_input_chars,
        "summary": summary,
        "index_seconds": round(index_seconds, 1),
        "avg_query_ms": round(sum(query_times) / len(query_times) * 1000),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Качество эмбеддеров на русском корпусе (B1)")
    parser.add_argument("--url", action="append", default=[],
                        help="добавить службу (иначе — все настроенные)")
    parser.add_argument("--service", action="append", default=[],
                        help="запустить только выбранные службы (имя из SERVICES)")
    args = parser.parse_args()

    configs = dict(SERVICES)
    if args.service:
        configs = {k: v for k, v in SERVICES.items() if k in set(args.service)}
    for i, url in enumerate(args.url, start=1):
        configs[f"custom-{i}"] = {"url": url, "doc_prompt": "{t}", "query_prompt": "{q}"}

    results = []
    for name, config in configs.items():
        if not service_alive(config["url"]):
            print(f"--- {name}: служба {config['url']} не поднята — пропуск")
            continue
        print(f"--- {name} ({config['url']}) ---")
        result = evaluate(name, config)
        results.append(result)
        for qid, qset, target, rank, top_sim, target_sim in result["rows"]:
            if target == "—":
                print(f"  [cal] {qid} ({qset}): нет цели в корпусе, top sim {top_sim} "
                      "(чем ниже — тем честнее отказ)")
                continue
            mark = "ok " if rank == 1 else ("~  " if rank <= 3 else "FAIL")
            print(f"  [{mark}] {qid} ({qset}): цель {target} на месте {rank} "
                  f"(top sim {top_sim}, цель sim {target_sim})")
        for qset, s in result["summary"].items():
            print(f"  [{qset}] n={s['n']} hit@1={s['hit1']:.2f} hit@3={s['hit3']:.2f} "
                  f"hit@5={s['hit5']:.2f} MRR={s['mrr']:.2f}")
        print(f"  индексация {result['index_seconds']} c, запрос ~{result['avg_query_ms']} мс | "
              f"dim={result['dim']}, ворота={result['max_input_chars']} симв.")

    print("\n=== СВОДКА (easy/hard) ===")
    for r in results:
        parts = [f"{name}: hit@1={s['hit1']:.2f} MRR={s['mrr']:.2f}" for name, s in r["summary"].items()]
        print(f"{r['name']:22s} запрос~{r['avg_query_ms']}мс | " + " | ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
