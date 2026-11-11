import os
from uuid import UUID

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal, set_tenant_context
from app.models import AIAgent, Conversation, Customer, Message, Ticket
from app.models.knowledge_gap import KnowledgeGap
from app.models.knowledge_gap_group import KnowledgeGapGroup, KnowledgeGapGroupMember
from tests.test_ai_integration import approved_workspace, bearer, platform_owner

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Requires isolated PostgreSQL"),
]


async def seed_questions(organization_id: UUID) -> None:
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        customer = Customer(organization_id=organization_id, name="Customer")
        db.add(customer)
        await db.flush()
        ticket = Ticket(organization_id=organization_id, customer_id=customer.id, subject="Questions")
        db.add(ticket)
        await db.flush()
        agent_id = await db.scalar(select(AIAgent.id).where(
            AIAgent.organization_id == organization_id, AIAgent.is_default.is_(True),
        ))
        assert agent_id is not None
        conversation = Conversation(organization_id=organization_id, ticket_id=ticket.id, ai_agent_id=agent_id)
        db.add(conversation)
        await db.flush()
        group = KnowledgeGapGroup(organization_id=organization_id, representative="Returns")
        db.add(group)
        await db.flush()
        for question, status in (
            ("Can I return this?", "open"),
            ("Can I send it back?", "open"),
            ("When will it ship?", "open"),
            ("Do you offer exchanges?", "resolved"),
        ):
            message = Message(
                organization_id=organization_id, conversation_id=conversation.id,
                sender_type="customer", content=question,
            )
            db.add(message)
            await db.flush()
            gap = KnowledgeGap(
                organization_id=organization_id, source_message_id=message.id,
                question=question, status=status, reason="no_relevant_evidence",
            )
            db.add(gap)
            await db.flush()
            if question in ("Can I return this?", "Can I send it back?"):
                db.add(KnowledgeGapGroupMember(organization_id=organization_id, group_id=group.id, gap_id=gap.id))
        await db.commit()


async def test_dashboard_counts_views_search_pagination_and_tenant_scope(client):
    platform = await platform_owner(client)
    first = await approved_workspace(client, platform, "question-dashboard")
    second = await approved_workspace(client, platform, "question-empty")
    await seed_questions(UUID(first["user"]["organization_id"]))
    endpoint = "/api/v1/knowledge/gaps/dashboard"

    async def dashboard(workspace, **params):
        response = await client.get(endpoint, headers=bearer(workspace["access_token"]), params=params)
        assert response.status_code == 200, response.text
        return response.json()

    full = await dashboard(first)
    assert full["counts"] == {"total": 4, "open": 3, "resolved": 1, "grouped": 2, "groups": 1}
    assert not full["has_more"]
    grouped = await dashboard(first, view="grouped", limit=1)
    assert grouped["has_more"]
    assert grouped["items"][0]["representative"] == "Returns"
    assert len(grouped["items"][0]["questions"]) == 1
    ungrouped = await dashboard(first, view="ungrouped", search="SHIP")
    assert ungrouped["items"][0]["questions"][0]["question"] == "When will it ship?"
    assert (await dashboard(first, search="%"))["items"] == []
    assert (await dashboard(second))["counts"]["total"] == 0
