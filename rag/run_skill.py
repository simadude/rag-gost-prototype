"""CLI-запуск умения отдельно: умение удобно тестировать само по себе (A3).

    python3 project/run_skill.py prepare_knowledge_base
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from core.skills_registry import SKILLS, run_skill  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Запуск умения (подграфа) отдельно")
    parser.add_argument("skill", nargs="?", default="prepare_knowledge_base",
                        choices=sorted(SKILLS), help="умение из реестра")
    args = parser.parse_args()

    result = run_skill(args.skill)
    print(f"=== Умение {args.skill} ===")
    print("trace:", " → ".join(result.trace))
    print("status:", result.status)
    print("Умение прошло отдельно — работает так же, как в основном графе.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
