"""Release gate tests exercise both accepted and rejected corpora."""
import json
from pathlib import Path

from app.features.ai.application.rag_release_gate import evaluate_corpus_gate


def test_committed_corpus_meets_integrity_gate() -> None:
    result = evaluate_corpus_gate()
    assert result.passed, result.failures
    assert result.count >= 100


def test_duplicate_ids_and_missing_coverage_fail(tmp_path: Path) -> None:
    cases = [
        {"id": "duplicate", "question": "What is your return policy?", "category": "refunds"},
        {"id": "duplicate", "question": "Can I return it?", "category": "refunds"},
    ]
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(cases), encoding="utf-8")
    result = evaluate_corpus_gate(path)
    assert not result.passed
    assert "duplicate_case_ids" in result.failures
    assert any(failure.startswith("missing_categories:") for failure in result.failures)
    assert any(failure.startswith("corpus_too_small:") for failure in result.failures)


def test_inconsistent_retrieval_expectation_fails(tmp_path: Path) -> None:
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps([{
        "id": "wrong", "question": "Shipping?",
        "category": "shipping", "skip_retrieval": True,
        "expected_doc_terms": ["shipping"],
    }]), encoding="utf-8")
    result = evaluate_corpus_gate(path)
    assert "contradictory_retrieval_expectation:wrong" in result.failures
