"""Automation template catalog API shape and content invariants."""

from app.features.automations.template_catalog import list_templates


def test_list_templates_has_no_phase_field_and_sorts_by_category():
    rows = list_templates()
    assert rows, "expected at least one marketplace template"
    for row in rows:
        assert "phase" not in row
        assert "category" in row and "title" in row


def test_commerce_approval_template_id_is_stable():
    rows = list_templates()
    ids = {r["id"] for r in rows}
    assert "playbook-14-commerce-refund-approval" in ids
    assert "playbook-06-commerce-write-branch" not in ids
