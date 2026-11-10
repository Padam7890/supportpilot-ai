#!/usr/bin/env python3
"""Fail CI when the checked-in RAG evaluation corpus loses integrity."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.features.ai.application.rag_release_gate import evaluate_corpus_gate


def main() -> int:
    result = evaluate_corpus_gate()
    print(f"rag_corpus_gate={'PASS' if result.passed else 'FAIL'}")
    print(f"cases={result.count}")
    print("categories=" + ",".join(f"{name}:{count}" for name, count in result.categories.items()))
    for failure in result.failures:
        print(f"failure={failure}", file=sys.stderr)
    print("live_retrieval_recall=NOT_MEASURED")
    print("citation_validity=NOT_MEASURED")
    print("answer_grounding=NOT_MEASURED")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
