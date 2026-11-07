import pytest
from pydantic import ValidationError

from app.schemas.ai_agents import AIAgentCreate, AIAgentUpdate
from app.schemas.knowledge_bases import KnowledgeBaseCreate, KnowledgeBaseUpdate


@pytest.mark.parametrize(
    "schema,payload",
    [
        (KnowledgeBaseCreate, {"name": "   "}),
        (KnowledgeBaseUpdate, {"name": "\t\n"}),
        (AIAgentCreate, {"name": "   "}),
        (AIAgentUpdate, {"name": "\t\n"}),
    ],
)
def test_configuration_names_reject_whitespace_only(schema, payload):
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


@pytest.mark.parametrize(
    "schema,payload",
    [
        (KnowledgeBaseCreate, {"name": "  Returns policy  "}),
        (KnowledgeBaseUpdate, {"name": "  Product help  "}),
        (AIAgentCreate, {"name": "  Returns bot  "}),
        (AIAgentUpdate, {"name": "  Product bot  "}),
    ],
)
def test_configuration_names_are_normalized(schema, payload):
    result = schema.model_validate(payload)
    assert result.name == payload["name"].strip()
