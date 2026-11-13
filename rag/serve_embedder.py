"""Служба эмбеддера за внешним контуром: обёртка локальной модели под наш коннектор (B1).

Позволяет подключить скачанную эмбеддинг-модель (HuggingFace/локальная папка)
к системе как службу за внешним контуром — коннектор `providers/embedder.py`
(RAG_EMBEDDER=http, RAG_EMBEDDER_URL) ходит именно по этому договору:

    POST /         {"texts": [...]}          → {"vectors": [[...], ...]}
    GET  /limits                             → {"limits": {"model", "dim",
                                                "max_input_chars", "max_batch"}}

Запуск:
    python3 project/serve_embedder.py --model intfloat/multilingual-e5-base --port 8123
    python3 project/serve_embedder.py --model /путь/к/скачанной/модели --max-chars 4096

Зависимости модели (ставятся отдельно, в скелет не притягиваются):
    pip install sentence-transformers
Модель выбирается специализированной под функцию/домен, не мультимодальной
(B1, встреча №3 15:41–23:06). Лимит длины входа (--max-chars) — входные ворота:
чанкер режет под него (`embed_chunks` ↔ `chunk_text`).
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_ARGS = argparse.Namespace(model="", max_chars=8192, max_batch=64)
_MODEL = None
_DIM = 0


def _encode(texts: list[str]) -> list[list[float]]:
    """Кодирует тексты моделью; векторы нормализованы (косинусная близость)."""
    limit = _ARGS.max_chars
    safe = [t[:limit] for t in texts]  # страховка: модель truncates сама, но режем по воротам
    vectors = _MODEL.encode(safe, batch_size=_ARGS.max_batch, normalize_embeddings=True)
    return [[float(x) for x in vector] for vector in vectors]


class Handler(BaseHTTPRequestHandler):
    """HTTP-договор службы эмбеддера (см. providers/embedder.HttpEmbedder)."""

    def _reply(self, code: int, body: dict) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - API http.server
        if self.path.rstrip("/") == "/limits":
            self._reply(200, {"limits": {
                "model": _ARGS.model,
                "dim": _DIM,
                "max_input_chars": _ARGS.max_chars,
                "max_batch": _ARGS.max_batch,
            }})
        else:
            self._reply(404, {"error": "только GET /limits и POST /"})

    def do_POST(self) -> None:  # noqa: N802 - API http.server
        if self.path.rstrip("/") != "/":
            self._reply(404, {"error": "только POST /"})
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            texts = [str(t) for t in body["texts"]]
        except Exception as exc:  # noqa: BLE001 - кривой запрос → 400
            self._reply(400, {"error": f"неверный запрос: {exc}"})
            return
        if not texts:
            self._reply(400, {"error": "пустой texts"})
            return
        if len(texts) > _ARGS.max_batch:
            self._reply(413, {"error": f"батч {len(texts)} > max_batch {_ARGS.max_batch}"})
            return
        self._reply(200, {"vectors": _encode(texts)})

    def log_message(self, fmt, *args) -> None:  # тише в консоли
        print(f"[embedder-service] {fmt % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Служба эмбеддера за внешним контуром (B1)")
    parser.add_argument("--model", required=True,
                        help="имя на HuggingFace или путь к скачанной модели")
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--max-chars", type=int, default=8192,
                        help="входные ворота: лимит длины входа (символы)")
    parser.add_argument("--max-batch", type=int, default=64)
    global _ARGS, _MODEL, _DIM
    _ARGS = parser.parse_args()

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("Нет sentence-transformers: pip install sentence-transformers")
        return 2

    print(f"[embedder-service] загружаю модель {_ARGS.model} …")
    _MODEL = SentenceTransformer(_ARGS.model)
    _DIM = int(_MODEL.get_sentence_embedding_dimension() or 0)
    if not _DIM:  # запасной путь: пробы на одном тексте
        _DIM = len(_MODEL.encode(["проба"], normalize_embeddings=True)[0])
    print(f"[embedder-service] модель готова: dim={_DIM}, "
          f"max_input_chars={_ARGS.max_chars}, max_batch={_ARGS.max_batch}")

    server = ThreadingHTTPServer(("127.0.0.1", _ARGS.port), Handler)
    print(f"[embedder-service] слушаю http://127.0.0.1:{_ARGS.port} "
          "(RAG_EMBEDDER_URL=http://127.0.0.1:%d)" % _ARGS.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[embedder-service] остановлена")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
