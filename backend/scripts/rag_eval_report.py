#!/usr/bin/env python3
"""Print a deterministic RAG evaluation summary from the JSON corpus (no model calls)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.features.ai.application.rag_eval import load_eval_corpus
from app.features.ai.application.retrieval import build_retrieval_terms, should_skip_semantic_retrieval


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize RAG eval corpus coverage")
    parser.parse_args()
    cases = load_eval_corpus()
    print(f"cases={len(cases)}")
    by_category: dict[str, int] = {}
    intent_hits = 0
    semantic_skips = 0
    for case in cases:
        by_category[case.category] = by_category.get(case.category, 0) + 1
        if case.expected_doc_terms:
            expanded = {term.casefold() for term in build_retrieval_terms(case.question)}
            expected = {term.casefold() for term in case.expected_doc_terms}
            if expected & expanded:
                intent_hits += 1
        if should_skip_semantic_retrieval(case.question) or case.skip_semantic:
            semantic_skips += 1
    print("categories=" + ", ".join(f"{key}:{count}" for key, count in sorted(by_category.items())))
    with_terms = sum(1 for case in cases if case.expected_doc_terms)
    if with_terms:
        print(f"intent_term_overlap={intent_hits}/{with_terms}")
    print(f"semantic_skip_eligible={semantic_skips}/{len(cases)}")


if __name__ == "__main__":
    main()
