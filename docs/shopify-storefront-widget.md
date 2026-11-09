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
- Auto-reply sends grounded answers when tenant knowledge search finds matching sources. Greetings, thanks, and capability questions get concise deterministic replies; unsupported policy/product questions receive a specific clarification or handoff instead of the same generic line. If model generation fails after its retry limit, the shopper receives a safe handoff message.
- Store-specific policies and product facts must be added and published in **Dashboard → Knowledge** before the assistant can answer them. It will not invent shipping terms, prices, stock, return eligibility, or other merchant facts. Live Shopify product lookup is unavailable until the app has the required product scope.
- Order and tracking questions show a contextual **Verify your order** card. SupportPilot matches the order number and checkout email against Shopify, then emails a one-time code to the matching checkout address. Tracking is shown only after the code is verified. A typed email or order number alone is not proof.
- After code verification, the visitor can ask follow-up status questions about that same order for the remaining verification window without entering another code. A different order requires a new verification. The conversation API exposes only whether verification is active; order details stay server-side until Shopify confirms them again.
- After verification, a cancellation request creates a pending Shopify cancellation action in the existing operations approval queue. An Owner/Admin must approve it; refund, restock, and customer notification are off by default. The AI never executes the mutation itself.
- Refund, payment, account-change, and unsupported requests that need an action are handed to the support team. Policy questions use published tenant knowledge; no Shopify product data is queried because the current app has no `read_products` scope.
- Before an auto reply is sent, the worker locks the conversation and checks for a newer customer message or teammate response. Disabling or changing AI settings while a job runs also prevents an unintended send.
- The visitor sees assistant messages through the existing thread poll. Draft-only results are visible only to the support team until an agent sends them.

## Install safely on Shopify

1. In Shopify Admin, duplicate the current theme. Test on the unpublished duplicate first.
2. Open **Online Store → Themes → (duplicated theme) → Edit code** and add the current versioned snippet from SupportPilot settings immediately before `</body>` in `layout/theme.liquid`. Replace any older SupportPilot script tag so Shopify does not keep loading a cached widget bundle.
3. Save and preview the duplicate theme. Send a test message and confirm it appears in SupportPilot **Inbox** (the current inbox refreshes periodically). Do not publish the duplicate until the test passes.
4. To remove the widget, remove the script tag from that theme. Disable the widget in SupportPilot to invalidate visitor sessions immediately.

## Enable verified order lookup

The backend needs transactional email settings before it can send verification codes. Configure these in the root `.env` for Compose, or `backend/.env` when running FastAPI directly:

```dotenv
EMAIL_SMTP_HOST=smtp.example.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=your-smtp-username
EMAIL_SMTP_PASSWORD=your-smtp-password
EMAIL_FROM_ADDRESS=support@your-domain.example
EMAIL_USE_SSL=false
```

Port 587 uses STARTTLS. For implicit TLS, use port 465 and `EMAIL_USE_SSL=true`. Keep the credentials server-side. Apply migrations through `0021_widget_order_consent`, then reload the backend and worker so they use the new routes and worker policy. The widget returns a generic response for order matches and non-matches; codes expire after 10 minutes and allow at most five attempts. Verification is limited to three code requests per conversation per ten minutes.

For AI replies, configure `AI_PROVIDER_BASE_URL`, `AI_PROVIDER_API_KEY`, and `AI_MODEL` in `backend/.env`. Docker Compose passes this file to the API and background worker; direct backend runs also read it. Use a server-side OpenAI-compatible chat-completions endpoint. Keep the key out of storefront JavaScript and Next.js public environment variables. Set the widget to `auto_reply` to send replies to shoppers; `draft_only` intentionally keeps responses in the SupportPilot Inbox for an agent.

The snippet resembles:

```html
<script async src="https://supportpilot.example/supportpilot-widget.js"
  data-widget-id="PUBLIC_WIDGET_ID"
  data-api-base="https://supportpilot.example/api"></script>
```

## Visitor and privacy behavior

- Initial messages require an allowlisted `Origin`, a per-widget/IP Redis rate limit, validated short text, an empty honeypot field, and a client `Idempotency-Key`.
- The origin allowlist and public widget ID are defense-in-depth/configuration only. Neither is treated as authentication. The backend issues a signed visitor token scoped to one conversation for 24 hours; that token is required to read or continue the conversation.
- Name/email are optional. If either is provided, the visitor must check the explicit contact consent box. For an order lookup, the shopper must provide the order number and checkout email, then verify a one-time code sent to the email Shopify has on that order. Order details are not returned before code verification.
- The widget stores its visitor token in tab-scoped `sessionStorage`; it never receives workspace or Shopify tokens. Internal notes and AI drafts are not returned to widget visitors.
- Public widget messages can trigger AI only after an Owner/Admin enables the feature. Internal notes and credentials are never included in visitor responses.

## Local API contract

- `GET /api/v1/widget/{public_id}/config`
- `POST /api/v1/widget/{public_id}/messages` with `Idempotency-Key`
- `GET /api/v1/widget/conversations/{conversation_id}` with the visitor bearer token
- `POST /api/v1/widget/conversations/{conversation_id}/messages` with the visitor bearer token and `Idempotency-Key`
- `POST /api/v1/widget/conversations/{conversation_id}/order-verification` with order number and checkout email
- `POST /api/v1/widget/conversations/{conversation_id}/order-verification/confirm` with the emailed six-digit code
- `POST /api/v1/widget/conversations/{conversation_id}/cancellation-request` with the visitor bearer token and idempotency key
- Owner/Admin management: `GET|POST|PUT /api/v1/integrations/widget`

First-message tickets use source `shopify_widget`, status `open`, and a `shopify_widget` conversation channel. Submission receipts are tenant-scoped and preserve idempotency without storing the raw client key. A repeated first request with the same key and payload returns the same ticket/conversation; reusing a key with different content returns `409`.

## Diagnose grounded reply failures in Docker Compose

The widget may find matching articles before the provider rejects the generation
request. The worker records retrieval and provider failures separately. The
shopper receives the existing handoff message, while operators can use the safe
reason codes in the worker logs.

1. Set `AI_PROVIDER_BASE_URL`, `AI_MODEL`, and `AI_PROVIDER_API_KEY` in
   `backend/.env`. Use the provider base URL, for example
   `https://api.openai.com/v1`. Replace an expired or revoked key with a valid
   key for the project. Keep credentials out of the shell command and chat.
2. Recreate the containers after changing the environment. A Docker restart
   retains the environment captured when a container was created.

   ```sh
   docker compose up -d --no-deps --force-recreate api worker
   docker compose ps api worker
   ```

3. Run the synthetic probe from the worker. These commands send a short prompt
   and print only success or safe diagnostics.

   ```sh
   docker compose exec -T worker python -m scripts.check_ai_provider
   docker compose exec -T worker python -m scripts.check_ai_provider --stream
   ```

4. Ask the widget a question covered by an assigned ready article, then inspect
   the worker's execution and retry decisions.

   ```sh
   docker compose logs --since=10m worker | rg 'worker_ai_provider_configuration|ai_knowledge_retrieval_completed|ai_execution_failed|ai_execution_retry_decision|ai_stream_'
   ```

A `provider_http_401` response with `expired_secret_key` requires key replacement.
A transient timeout or rate limit can be retried within the configured attempt
limit. Known quota and spend limits require an account change. A local
`configured=true` startup record only confirms that settings are present and
valid in format. The probe verifies actual model access.
