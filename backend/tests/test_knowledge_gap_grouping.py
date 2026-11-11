from uuid import UUID

import pytest

from app.features.ai.application.knowledge_gap_grouping import cosine_similarity, group_vectors


def test_cosine_similarity():
    assert cosine_similarity([1, 0], [1, 0]) == pytest.approx(1)
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0)


def test_groups_semantically_similar_vectors():
    questions = [
        (UUID(int=1), "Do you deliver to Pokhara?"),
        (UUID(int=2), "Is shipping available in Pokhara?"),
        (UUID(int=3), "Can I return my order?"),
    ]
    result = group_vectors(questions, [[1, 0], [0.99, 0.01], [0, 1]])
    assert [g.count for g in result] == [2, 1]
    assert result[0].gap_ids == (UUID(int=1), UUID(int=2))


def test_rejects_mismatched_embeddings():
    with pytest.raises(ValueError):
        group_vectors([(UUID(int=1), "Question")], [])
