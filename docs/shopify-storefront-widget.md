# Shopify storefront chat widget

The widget creates a tenant-scoped customer, open ticket, `shopify_widget` conversation, and initial customer message in one PostgreSQL transaction. Later visitor messages reuse the conversation. AI reply processing is queued only when a workspace Owner/Admin enables it in widget settings.

## Configure

1. Apply migrations locally with the project’s configured database: `cd backend && .venv/bin/alembic upgrade head`.
2. Start the existing backend, Redis, and Next.js processes using your usual local workflow. This setup does not require starting or restarting Docker.
3. Open **Dashboard → Settings & team → Shopify storefront chat** as an Owner/Admin.
4. Add the exact storefront origin, for example `https://your-store.myshopify.com`, and create the widget. The browser-visible widget ID only resolves its configuration; it is not an authorization credential.
5. If the storefront is remote and SupportPilot is local, set `NEXT_PUBLIC_SUPPORTPILOT_APP_URL` to an HTTPS tunnel URL that reaches Next.js, then restart the Next.js process. The widget uses the Next.js `/api/widget/*` proxy; the backend separately checks the incoming origin against the configured allowlist. Never put Shopify credentials in this snippet.
6. In widget settings, enable AI replies and choose `draft_only` or `auto_reply`. AI is disabled until opted in; draft-only is the default mode. The AI provider must be configured on the backend.

## AI reply behavior

- New widget messages create durable, idempotent AI jobs. The customer message request does not wait for the model.
- Draft-only responses appear in the Inbox with citations and require an agent to insert and send them.
- Auto-reply sends only when tenant knowledge search finds matching sources. The worker bounds response length and stores token usage.
- Order, tracking, cancellation, refund, payment, account, and unsupported requests are escalated. A typed email or order number from the widget is never proof of identity; widget AI does not execute Shopify mutations.
- Before an auto reply is sent, the worker locks the conversation and checks for a newer customer message or teammate response. Disabling or changing AI settings while a job runs also prevents an unintended send.
- The visitor sees assistant messages through the existing thread poll. Draft-only results are visible only to the support team until an agent sends them.

## Install safely on Shopify

1. In Shopify Admin, duplicate the current theme. Test on the unpublished duplicate first.
2. Open **Online Store → Themes → (duplicated theme) → Edit code** and add the snippet from SupportPilot settings immediately before `</body>` in `layout/theme.liquid`.
3. Save and preview the duplicate theme. Send a test message and confirm it appears in SupportPilot **Inbox** (the current inbox refreshes periodically). Do not publish the duplicate until the test passes.
4. To remove the widget, remove the script tag from that theme. Disable the widget in SupportPilot to invalidate visitor sessions immediately.

The snippet resembles:

```html
<script async src="https://supportpilot.example/supportpilot-widget.js"
  data-widget-id="PUBLIC_WIDGET_ID"
  data-api-base="https://supportpilot.example/api"></script>
```

## Visitor and privacy behavior

- Initial messages require an allowlisted `Origin`, a per-widget/IP Redis rate limit, validated short text, an empty honeypot field, and a client `Idempotency-Key`.
- The origin allowlist and public widget ID are defense-in-depth/configuration only. Neither is treated as authentication. The backend issues a signed visitor token scoped to one conversation for 24 hours; that token is required to read or continue the conversation.
- Name/email are optional. If either is provided, the visitor must check the explicit contact consent box. These values are contact details, not identity proof. The widget returns no Shopify customer/order information.
- The widget stores its visitor token in tab-scoped `sessionStorage`; it never receives workspace or Shopify tokens. Internal notes and AI drafts are not returned to widget visitors.
- Public widget messages can trigger AI only after an Owner/Admin enables the feature. Internal notes and credentials are never included in visitor responses.

## Local API contract

- `GET /api/v1/widget/{public_id}/config`
- `POST /api/v1/widget/{public_id}/messages` with `Idempotency-Key`
- `GET /api/v1/widget/conversations/{conversation_id}` with the visitor bearer token
- `POST /api/v1/widget/conversations/{conversation_id}/messages` with the visitor bearer token and `Idempotency-Key`
- Owner/Admin management: `GET|POST|PUT /api/v1/integrations/widget`

First-message tickets use source `shopify_widget`, status `open`, and a `shopify_widget` conversation channel. Submission receipts are tenant-scoped and preserve idempotency without storing the raw client key. A repeated first request with the same key and payload returns the same ticket/conversation; reusing a key with different content returns `409`.
