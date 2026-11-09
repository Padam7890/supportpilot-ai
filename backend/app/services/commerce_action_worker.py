"""Durable worker for approved mock-commerce actions."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select

from app.workers.domain.lease_policy import COMMERCE_ACTION_LEASE as ACTION_LEASE_TIMEOUT
from app.db.session import SessionLocal, set_tenant_context
from app.integrations.providers.shopify.actions import (
    ShopifyOrderActionError,
    cancel_shopify_order,
    check_cancellation_eligibility,
)
from app.integrations.providers.shopify.orders import lookup_authorized_order
from app.integrations.providers.shopify.security import decrypt_credential
from app.models import CommerceAction, CommerceActionAudit, Customer, ShopifyInstallation, Ticket
from app.services.mock_commerce import MockCommerceService
from app.services.commerce_action_recovery import decide_lease_recovery

logger = logging.getLogger(__name__)
MAX_EXECUTION_ATTEMPTS = 3


async def expire_one_pending_action(organization_id: UUID) -> bool:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        ids = await db.scalars(
            select(CommerceAction.id)
            .where(
                CommerceAction.organization_id == organization_id,
                CommerceAction.approval_status == "pending",
                CommerceAction.expires_at <= now,
            )
            .order_by(CommerceAction.expires_at, CommerceAction.id)
            .limit(25)
        )
        for action_id in ids:
            action = await db.scalar(
                select(CommerceAction)
                .where(
                    CommerceAction.organization_id == organization_id,
                    CommerceAction.id == action_id,
                    CommerceAction.approval_status == "pending",
                    CommerceAction.expires_at <= now,
                )
                .with_for_update(skip_locked=True)
            )
            if action is None:
                continue
            action.approval_status = "expired"
            db.add(
                CommerceActionAudit(
                    organization_id=organization_id,
                    commerce_action_id=action.id,
                    actor_user_id=None,
                    event_type="expired",
                    details={"reason": "approval_window_elapsed"},
                )
            )
            await db.commit()
            return True
        await db.rollback()
        return False


async def claim_commerce_action(organization_id: UUID) -> UUID | None:
    now = datetime.now(UTC)
    lease_expired = now - ACTION_LEASE_TIMEOUT
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        ids = await db.scalars(
            select(CommerceAction.id)
            .where(
                CommerceAction.organization_id == organization_id,
                CommerceAction.approval_status == "approved",
                or_(
                    CommerceAction.execution_status == "queued",
                    and_(
                        CommerceAction.execution_status == "running",
                        CommerceAction.updated_at <= lease_expired,
                    ),
                ),
            )
            .order_by(CommerceAction.created_at, CommerceAction.id)
            .limit(25)
        )
        for action_id in ids:
            action = await db.scalar(
                select(CommerceAction)
                .where(
                    CommerceAction.organization_id == organization_id,
                    CommerceAction.id == action_id,
                    CommerceAction.approval_status == "approved",
                )
                .with_for_update(skip_locked=True)
            )
            if action is None:
                continue
            is_queued = action.execution_status == "queued"
            is_reclaimable = (
                action.execution_status == "running"
                and action.updated_at <= lease_expired
            )
            if not (is_queued or is_reclaimable):
                continue
            # Shopify cancellations are non-idempotent at the provider boundary.
            # A timed-out lease can mean Shopify accepted the mutation while our
            # worker crashed before committing success. Never dispatch it again.
            recovery = decide_lease_recovery(
                provider=action.provider,
                status=action.execution_status,
                lease_expired=is_reclaimable,
                attempts=action.execution_attempt_count,
                max_attempts=MAX_EXECUTION_ATTEMPTS,
            )
            if recovery == "manual_reconciliation":
                action.execution_status = "failed"
                action.execution_error_code = "shopify_outcome_unknown_manual_review"
                action.execution_completed_at = now
                db.add(
                    CommerceActionAudit(
                        organization_id=organization_id,
                        commerce_action_id=action.id,
                        actor_user_id=None,
                        event_type="execution_failed",
                        details={
                            "error_code": action.execution_error_code,
                            "attempt": action.execution_attempt_count,
                            "manual_reconciliation_required": True,
                        },
                    )
                )
                await db.commit()
                return None
            if recovery == "retry_limit":
                action.execution_status = "failed"
                action.execution_error_code = "worker_lease_retry_limit"
                action.execution_completed_at = now
                db.add(
                    CommerceActionAudit(
                        organization_id=organization_id,
                        commerce_action_id=action.id,
                        actor_user_id=None,
                        event_type="execution_failed",
                        details={"error_code": action.execution_error_code},
                    )
                )
                await db.commit()
                return None
            action.execution_status = "running"
            action.execution_attempt_count += 1
            action.execution_started_at = action.execution_started_at or now
            db.add(
                CommerceActionAudit(
                    organization_id=organization_id,
                    commerce_action_id=action.id,
                    actor_user_id=None,
                    event_type="execution_started",
                    details={"attempt": action.execution_attempt_count},
                )
            )
            await db.commit()
            return action.id
        await db.rollback()
        return None


async def fail_exhausted_action_leases(organization_id: UUID) -> bool:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        action = await db.scalar(
            select(CommerceAction)
            .where(
                CommerceAction.organization_id == organization_id,
                CommerceAction.approval_status == "approved",
                CommerceAction.execution_status == "running",
                CommerceAction.execution_attempt_count >= MAX_EXECUTION_ATTEMPTS,
                CommerceAction.updated_at <= now - ACTION_LEASE_TIMEOUT,
            )
            .order_by(CommerceAction.updated_at, CommerceAction.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if action is None:
            await db.rollback()
            return False
        action.execution_status = "failed"
        action.execution_error_code = (
            "shopify_outcome_unknown_manual_review"
            if action.provider == "shopify"
            else "worker_lease_retry_limit"
        )
        action.execution_completed_at = now
        db.add(
            CommerceActionAudit(
                organization_id=organization_id,
                commerce_action_id=action.id,
                actor_user_id=None,
                event_type="execution_failed",
                details={"error_code": action.execution_error_code},
            )
        )
        await db.commit()
        return True


async def process_commerce_action(organization_id: UUID, action_id: UUID) -> None:
    correlation_id: str | None = None
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        action = await db.scalar(
            select(CommerceAction).where(
                CommerceAction.organization_id == organization_id,
                CommerceAction.id == action_id,
                CommerceAction.approval_status == "approved",
                CommerceAction.execution_status == "running",
            )
        )
        if action is None:
            await db.rollback()
            return
        correlation_id = action.correlation_id
        operation = {
            "idempotency_key_hash": action.idempotency_key_hash,
            "action_type": action.action_type,
            "provider": action.provider,
            "order_number": action.order_number,
            "shopify_order_id": action.shopify_order_id,
            "refund_amount": action.refund_amount,
            "currency": action.currency,
            "reason": action.reason,
            "cancel_refund": action.cancel_refund,
            "cancel_restock": action.cancel_restock,
            "cancel_notify_customer": action.cancel_notify_customer,
            "cancellation_reason": action.cancellation_reason,
        }
        if action.provider == "shopify":
            connection = await db.get(ShopifyInstallation, organization_id)
            if (
                connection is None
                or connection.disconnected_at is not None
                or connection.access_token_encrypted is None
            ):
                operation["shopify_error"] = "shopify_connection_unavailable"
            elif "write_orders" not in set(connection.granted_scopes):
                operation["shopify_error"] = "shopify_cancel_permission_denied"
            elif (
                connection.access_token_expires_at is None
                or connection.access_token_expires_at <= datetime.now(UTC)
            ):
                operation["shopify_error"] = "shopify_reconnect_required"
            else:
                operation["shop_domain"] = connection.shop_domain
                try:
                    operation["access_token"] = decrypt_credential(connection.access_token_encrypted)
                except RuntimeError:
                    operation["shopify_error"] = "shopify_credentials_unavailable"
            linked = await db.execute(
                select(Customer.email)
                .join(
                    Ticket,
                    (Ticket.organization_id == Customer.organization_id)
                    & (Ticket.customer_id == Customer.id),
                )
                .where(
                    Ticket.organization_id == organization_id,
                    Ticket.id == action.ticket_id,
                )
            )
            operation["customer_email"] = linked.scalar_one_or_none()
        await db.rollback()

    try:
        if operation["provider"] == "shopify":
            if operation.get("shopify_error"):
                raise ShopifyOrderActionError(operation["shopify_error"])
            customer_email = operation.get("customer_email")
            if not isinstance(customer_email, str) or not customer_email:
                raise ShopifyOrderActionError("shopify_customer_identity_unavailable")
            order = await lookup_authorized_order(
                shop_domain=operation["shop_domain"],
                access_token=operation["access_token"],
                order_number=operation["order_number"],
                customer_email=customer_email,
            )
            if order is None or order.get("id") != operation["shopify_order_id"]:
                raise ShopifyOrderActionError("shopify_order_verification_failed")
            check_cancellation_eligibility(order)
            result = await cancel_shopify_order(
                shop_domain=operation["shop_domain"],
                access_token=operation["access_token"],
                order_id=operation["shopify_order_id"],
                notify_customer=operation["cancel_notify_customer"],
                refund=operation["cancel_refund"],
                restock=operation["cancel_restock"],
                reason=operation["cancellation_reason"],
                staff_note=operation["reason"],
            )
            result.update({
                "order_number": operation["order_number"],
                "refund": operation["cancel_refund"],
                "restock": operation["cancel_restock"],
                "notify_customer": operation["cancel_notify_customer"],
            })
        else:
            # Keep the adapter boundary explicit: ``operation`` also contains
            # provider-specific Shopify credentials and cancellation options.
            # Passing the whole dict broke the mock adapter's narrower contract.
            result = await MockCommerceService().execute(
                idempotency_key_hash=operation["idempotency_key_hash"],
                action_type=operation["action_type"],
                order_number=operation["order_number"],
                refund_amount=operation["refund_amount"],
                currency=operation["currency"],
            )
    except Exception as exc:  # noqa: BLE001 - persist failures for every adapter error.
        error_code = exc.code if isinstance(exc, ShopifyOrderActionError) else (
            "mock_commerce_failed" if operation["provider"] == "mock" else "shopify_cancel_provider_error"
        )
        logger.warning(
            "Commerce action execution failed",
            extra={
                "commerce_action_id": str(action_id),
                "organization_id": str(organization_id),
                "correlation_id": correlation_id,
                "error_type": type(exc).__name__,
            },
        )
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            action = await db.scalar(
                select(CommerceAction)
                .where(
                    CommerceAction.organization_id == organization_id,
                    CommerceAction.id == action_id,
                )
                .with_for_update()
            )
            if action is None or action.execution_status != "running":
                await db.rollback()
                return
            # Never automatically resend an ambiguous Shopify cancellation.
            exhausted = operation["provider"] == "shopify" or action.execution_attempt_count >= MAX_EXECUTION_ATTEMPTS
            action.execution_status = "failed" if exhausted else "queued"
            action.execution_error_code = error_code if exhausted else "mock_commerce_retryable_failure"
            action.execution_completed_at = datetime.now(UTC) if exhausted else None
            db.add(
                CommerceActionAudit(
                    organization_id=organization_id,
                    commerce_action_id=action.id,
                    actor_user_id=None,
                    event_type="execution_failed" if exhausted else "execution_retry_scheduled",
                    details={
                        "error_code": action.execution_error_code,
                        "attempt": action.execution_attempt_count,
                        "max_attempts": MAX_EXECUTION_ATTEMPTS,
                        "provider": action.provider,
                    },
                )
            )
            await db.commit()
        return

    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        action = await db.scalar(
            select(CommerceAction)
            .where(
                CommerceAction.organization_id == organization_id,
                CommerceAction.id == action_id,
            )
            .with_for_update()
        )
        if action is None or action.execution_status != "running":
            await db.rollback()
            return
        action.execution_status = "succeeded"
        action.execution_result = result
        action.execution_error_code = None
        action.execution_completed_at = datetime.now(UTC)
        db.add(
            CommerceActionAudit(
                organization_id=organization_id,
                commerce_action_id=action.id,
                actor_user_id=None,
                event_type="execution_succeeded",
                details={
                    "provider": result.get("provider"),
                    "operation_id": result.get("operation_id"),
                    "order_id": result.get("order_id", action.shopify_order_id),
                    "order_number": action.order_number,
                    "action_type": action.action_type,
                    "shopify_result": result if result.get("provider") == "shopify" else None,
                },
            )
        )
        await db.commit()
