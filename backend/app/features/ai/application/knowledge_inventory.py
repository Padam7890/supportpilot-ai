"""Deterministic source inventory for authenticated AI Playground requests."""

import re
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIAgent, AIAgentKnowledgeBase, KnowledgeBase, KnowledgeDocument

_INVENTORY_QUESTION = re.compile(
    r"\b(?:what|which|show|list)\b.{0,48}\b(?:docs?|documents?|sources?|knowledge bases?|files?)\b"
    r"|\b(?:docs?|documents?|sources?|knowledge bases?|files?)\b.{0,48}\b(?:do you have|are available|can you access|can this bot use|is assigned)\b"
    r"|(?:कुन(?: कुन)?|के(?: के)?|देखाउ|देखाउनु|सूची).{0,48}(?:कागजात|दस्तावेज|डोकुमेन्ट|स्रोत|फाइल|ज्ञान आधार|जानकारी)"
    r"|(?:कागजात|दस्तावेज|डोकुमेन्ट|स्रोत|फाइल|ज्ञान आधार).{0,48}(?:छ|छन्|उपलब्ध|हेर्न|प्रयोग|पहुँच)"
    r"|\b(?:kun(?: kun)?|ke(?: ke)?|k k|dekhauna|dekhau|list|show)\b.{0,48}\b(?:docs?|document|source|file|knowledge)\b"
    r"|\b(?:docs?|documents?|sources?|files?|knowledge)\b.{0,48}\b(?:cha|chha|chan|available|access|use|assigned|have)\b",
    re.IGNORECASE,
)
_CONTENT_QUALIFIER = re.compile(
    r"\b(?:about|for|on|regarding|covering)\b|"
    r"\b(?:ko barema|barema|bisayama|sambandhi)\b|(?:बारेमा|विषयमा|सम्बन्धी)",
    re.IGNORECASE,
)


def is_knowledge_inventory_question(question: str) -> bool:
    """Match questions about assigned source names, not questions about their content."""
    normalized = question.strip()
    return bool(_INVENTORY_QUESTION.search(normalized)) and not _CONTENT_QUALIFIER.search(normalized)


async def load_knowledge_inventory(
    db: AsyncSession,
    *,
    organization_id: UUID,
    ai_agent_id: UUID | None,
) -> dict[str, tuple[int, list[str]]]:
    """Return ready document counts and bounded names for active assigned bases."""
    if ai_agent_id is None:
        return {}

    base_documents = (
        select(
            KnowledgeBase.id.label("base_id"),
            KnowledgeBase.name.label("base_name"),
            KnowledgeDocument.name.label("document_name"),
            func.count(KnowledgeDocument.id)
            .over(partition_by=KnowledgeBase.id)
            .label("document_count"),
            func.row_number()
            .over(partition_by=KnowledgeBase.id, order_by=KnowledgeDocument.name)
            .label("document_rank"),
        )
        .join(
            AIAgent,
            (AIAgent.organization_id == KnowledgeBase.organization_id)
            & (AIAgent.id == ai_agent_id)
            & (AIAgent.status == "active"),
        )
        .join(
            AIAgentKnowledgeBase,
            (AIAgentKnowledgeBase.organization_id == KnowledgeBase.organization_id)
            & (AIAgentKnowledgeBase.knowledge_base_id == KnowledgeBase.id),
        )
        .outerjoin(
            KnowledgeDocument,
            (KnowledgeDocument.organization_id == KnowledgeBase.organization_id)
            & (KnowledgeDocument.knowledge_base_id == KnowledgeBase.id)
            & (KnowledgeDocument.status == "ready")
            & KnowledgeDocument.deleted_at.is_(None),
        )
        .where(
            KnowledgeBase.organization_id == organization_id,
            KnowledgeBase.status == "active",
            AIAgent.organization_id == organization_id,
            AIAgentKnowledgeBase.organization_id == organization_id,
            AIAgentKnowledgeBase.ai_agent_id == AIAgent.id,
            AIAgentKnowledgeBase.ai_agent_id == ai_agent_id,
        )
        .subquery()
    )
    rows = (
        await db.execute(
            select(
                base_documents.c.base_name,
                base_documents.c.document_name,
                base_documents.c.document_count,
            )
            .where(base_documents.c.document_rank <= 8)
            .order_by(base_documents.c.base_name, base_documents.c.document_name)
        )
    ).all()

    inventory: dict[str, tuple[int, list[str]]] = {}
    for base_name, document_name, document_count in rows:
        total, names = inventory.setdefault(base_name, (int(document_count), []))
        if document_name is not None:
            names.append(document_name)
        inventory[base_name] = (total, names)
    return inventory


def format_knowledge_inventory(
    inventory: dict[str, tuple[int, list[str]]],
) -> tuple[str, int]:
    """Format a metadata-only answer and return the exact ready-document count."""
    document_count = sum(count for count, _names in inventory.values())
    if not inventory or document_count == 0:
        return (
            ("This AI bot has no ready documents in its assigned active knowledge bases yet. "
             "Add a document to an assigned base, or assign an active base to this bot."),
            0,
        )

    sections = []
    for base_name, (total, document_names) in inventory.items():
        if document_names:
            names = ", ".join(document_names)
            remaining = total - len(document_names)
            if remaining > 0:
                names += f", and {remaining} more"
            sections.append(f"{base_name}: {names}")
        else:
            sections.append(f"{base_name}: no ready documents")
    answer = "This AI bot can access these assigned knowledge sources:\n" + "\n".join(
        f"• {section}" for section in sections
    )
    return answer[:4000], document_count
