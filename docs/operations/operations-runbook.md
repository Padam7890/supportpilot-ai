# SupportPilot AI Operations Runbook

This runbook covers the operational signals currently exposed in the Operations and Analytics screens. Counts are workspace-scoped persisted records, not a guarantee that an external provider or worker is currently healthy. The Operations page is available at `/dashboard/operations`.

The 24-hour window uses the terminal completion timestamp for jobs currently marked failed. If an older record has no completion timestamp, Operations uses its last update time, as it does in Failed jobs.

## First response

1. Open **Operations → Operational activity** and note the alert type, count, and 24-hour window.
2. Open **Failed jobs** for individual terminal failures. Review only the stable error code, attempt count, and resource type shown there.
3. If a job has a correlation reference, choose **Trace** to view its tenant-scoped lifecycle. The trace intentionally omits prompts, messages, customer data, credentials, and provider payloads.
4. Confirm the dependency is healthy before retrying. Retrying a job that depends on a revoked credential or unavailable source file may fail again.
5. After remediation, use the existing retry action where available and refresh Operations to confirm the new state.

## Alerts

| Alert | Triage | Safe recovery |
| --- | --- | --- |
| AI runs failed | Review the AI execution error code and trace. Check provider configuration, model availability, and the selected bot's assigned active knowledge bases. | Retry an eligible AI execution from Failed jobs after the cause is corrected. An AI retry may create a new result; review it before sending to a customer. |
| Automation runs failed | Open Automations and inspect the execution history and failed node. Confirm the workflow version and configured action are still valid. | Correct the draft and publish a new version. Replay only when the workflow action is safe to repeat. |
| Catalog syncs failed | Open Integrations and inspect the Shopify connection status, catalog sync history, and sanitized error code. | Restore the connection or resolve the provider error, then retry the sync. Do not change requested scopes unless the actual provider response indicates a missing permission. |
| Catalog webhooks failed | Open Integrations and inspect the failed event and provider connection. Check whether a later event or a full sync already reconciled the product. | Retry only a verified event. The handler fetches current provider state and relies on event idempotency. |
| Outbound deliveries failed | Open delivery analytics and inspect the connection/provider status and stable error code. | Restore or reconnect the provider, then retry within the configured retry limit. Confirm the recipient/channel is correct before retrying. |
| Knowledge documents failed to process | Open Knowledge Library and inspect the document's processing history and source availability. The alert counts each document still marked failed once, even after multiple attempts. | Owners/Admins can reprocess a failed document when its source file is still available. Reprocessing retains the document and job history. |
| Commerce requests need review | Open the commerce action queue in Operations and review the request, order, and stated consequences. | An authorized Owner/Admin explicitly approves or rejects the request. Approval does not guarantee successful provider execution. |
| Commerce actions failed | Open the commerce action history and inspect the safe execution status and trace. Verify the Shopify connection and current order eligibility. | Resolve the provider or eligibility issue before using a supported retry/recovery path. Never repeat the mutation manually without checking the action's idempotency and authoritative order state. |

## Worker and readiness status

- **Worker inactive:** queued jobs may wait. Check the worker process and Redis connectivity using deployment tooling, then refresh the worker status card. Do not interpret an inactive heartbeat as proof that a particular job was lost.
- **Readiness unavailable:** inspect the database and Redis checks separately. A failed readiness request does not identify which tenant job failed; use job history and trace references for that.
- **No recent issues:** means no matching persisted terminal failures were counted in the last 24 hours and no unexpired commerce reviews were counted. It does not assert external provider uptime or zero transient errors.

## Correlation references and privacy

Correlation IDs connect a request to jobs created from it. Use **Trace** from a failed-job row or paste a reference into the Request trace panel. Results are restricted to the signed-in workspace and bounded to 100 job records. Older records may have no correlation ID. Never add access tokens, customer message contents, or full provider payloads to operational logs or support tickets.

## Operational limits

- Current alerts are in-product signals; paging/notification delivery is not configured here.
- Metrics are based on persisted operational records and do not replace provider dashboards or infrastructure monitoring.
- Database migration state and live deployment rollout must be checked using the deployment's approved release procedure; this runbook does not apply migrations or restart services.
