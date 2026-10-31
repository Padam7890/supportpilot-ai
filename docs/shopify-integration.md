# Shopify integration

SupportPilot connects one Shopify store to one workspace. For multi-tenant production connections, it uses Shopify's standalone-app OAuth authorization-code flow. Local development can instead use Shopify's server-side client-credentials grant for one configured, preinstalled store, without an authorization redirect. Credentials stay in FastAPI and access tokens are encrypted before persistence. The browser only sees the store domain, requested scopes, connection status, and verified order results.

## Development setup

1. Create/install the app in Shopify Dev Dashboard and request only `read_orders` and `read_customers`. Shopify can require separate protected-customer-data approval before customer name or email fields are returned.
2. For local development, set `SHOPIFY_STORE_DOMAIN`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, and a generated Fernet `SHOPIFY_ENCRYPTION_KEY` in the backend environment. The app and development store must belong to the same Shopify organization, and the app must already be installed on that store. The backend exchanges the app credentials directly for a short-lived token; no browser OAuth redirect is used. This fixed-store option is disabled outside `APP_ENV=development`.
3. For production/multi-tenant connections, also set `SHOPIFY_REDIRECT_URI` to the exact HTTPS callback configured in the app. Sign in as an Owner or Admin, open **Settings & team → Shopify**, enter the store's `*.myshopify.com` domain, and approve access in Shopify.
4. Generate encryption keys with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`. Keep all credentials out of browser variables and source control. Keep `SHOPIFY_API_VERSION` pinned to a supported stable GraphQL Admin API version.

The OAuth callback validates Shopify's HMAC, timestamp, state nonce, workspace/user binding, and exact shop domain. It requests expiring offline credentials, stores encrypted access and refresh tokens, and rotates both before expiry. In development client-credentials mode, the server renews the short-lived access token by repeating the grant. Disconnect removes stored tokens. Each Shopify store can be actively connected to only one SupportPilot workspace.

## Verified order facts in AI drafts

In the inbox reply composer, an agent may optionally provide an order number when requesting an AI draft. The server obtains the email from the CRM customer attached to the selected conversation, verifies the exact order-number/email pair with Shopify, and only then queues a draft. A minimal set of verified facts (order number, date, payment/fulfillment state, total, and tracking availability) is encrypted while the job is queued, passed as untrusted source data to the configured AI provider, and cleared when the job succeeds or exhausts retries. It is never returned in AI execution APIs; Shopify lookup results are still shown separately to the agent. Drafts are never sent automatically.

## Read-only order lookup

- `GET /api/v1/integrations/shopify/status` returns connection state and granted scopes.
- `GET /api/v1/integrations/shopify/orders/list?limit=25&cursor=...` returns one Shopify cursor page with order name, creation date, financial status, fulfillment status, and total. It omits customer fields and writes an access-audit record.
- `GET /api/v1/integrations/shopify/orders?customer_email=...&order_number=...` first requires an exact match on both values. Only after Shopify confirms that match does it return the matched order and a bounded page of that customer's recent order history.
- `GET /api/v1/integrations/shopify/orders/{order_number}?customer_email=...` returns a single order after the same verification.
- `POST /api/v1/integrations/shopify/disconnect` clears credentials and requires Owner/Admin access.

The backend's `lookup_authorized_order` service can be reused by future server-side agent tools. The caller must resolve the installation using the authenticated workspace organization and pass the customer email from an authorized SupportPilot customer/ticket record. An order number by itself never authorizes access.

Shopify order lookup remains read-only: no refund, cancellation, fulfillment, or other Shopify write API is exposed. SupportPilot has a separate human-reviewed commerce request workflow that verifies an order through the read-only connector, records approval and execution state independently, and runs approved requests through a deterministic mock commerce service. This simulation never changes the Shopify order. Shopify access audit rows keep the workspace user, time, resource type, result count, and a non-reversible query fingerprint; customer email is not copied into the audit log. The UI presents the order/email match before showing order history and tracking.

## Current verification boundary

Automated tests mock Shopify's OAuth token endpoint and GraphQL responses. A live development-store authorization and customer-data access check still requires the app credentials, HTTPS callback, development store, and any Shopify protected-customer-data approval. No Shopify credentials are committed in this repository.
