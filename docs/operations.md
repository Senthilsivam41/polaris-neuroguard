# Phase 7 Operations Runbook

## Signals and dashboard panels

Scrape `GET /metrics` with Prometheus. Build environment-separated dashboards using the deployment/environment label supplied by the scraper configuration.

- API latency: `polaris_api_request_seconds` p50, p95, and p99.
- Workflow latency: `polaris_workflow_seconds` p50, p95, and p99.
- Reliability: `polaris_workflow_executions_total`, `polaris_node_executions_total`, `polaris_api_timeouts_total`, `polaris_a2a_failures_total`, and HTTP status-labelled request counts.
- Decision quality: `polaris_drift_warnings_total`, `polaris_hitl_interruptions_total`, and `polaris_workflow_resumes_total` (use amendment/override outcomes to monitor false positives).
- Cost: `polaris_model_cost_usd_total`; set `MODEL_COST_PER_WORKFLOW_USD` to the provider's measured per-workflow estimate.
- Recovery: `polaris_workflow_resumes_total` by outcome.

## Alerts and ownership

| Alert | Threshold | Owner | Recovery |
|---|---:|---|---|
| Workflow failure | Any failure | platform-oncall | Inspect trace ID, ADK logs, then retry with the same idempotency key only after resolving the root cause. |
| High latency | workflow/API p95 > 2 s | platform-oncall | Check Gemini/A2A availability, request volume, and retry counts; scale or disable affected remote node. |
| Version conflicts | >=5 observed conflicts | platform-oncall | Check duplicate clients and retry behavior; retain the winning durable session version. |
| Stuck interruptions | >=5 interruptions | workflow-owner | Review checkpoint reason and apply an authorized resume or amendment decision. |
| Drift spike | sustained warning increase | product-owner | Review active storms, constraints, and false-positive overrides. |
| A2A outage | Any A2A failure | platform-oncall | Inspect the propagated trace ID and remote-node health, then fail over or disable the remote node. |
| Model cost | configured cumulative budget exceeded | platform-oncall | Verify usage, token accounting, and model selection before raising the budget. |

`GET /api/v1/operations/alerts` exposes the in-process threshold evaluation for authenticated operators.

## Alert routing (production wiring)

In-process evaluation is the source of truth for threshold logic. Production deployments should:

1. Scrape `GET /metrics` with Prometheus (separate scrape configs per environment label).
2. Mirror the table above as PrometheusRule / Alertmanager routes that page the listed owner.
3. Forward `X-Trace-Id` from the failing request into the page payload so on-call can correlate ADK logs.
4. Keep `AUTH_REQUIRED=true` on `/api/v1/operations/alerts`; operators use a scoped bearer token, not anonymous scrape credentials.

Until Alertmanager is wired, treat `GET /api/v1/operations/alerts` as the operator console and escalate manually using the Owner column.

## Trace handling

Clients may provide `X-Trace-Id`; otherwise the API creates one and returns it in the response header. Include it when escalating an incident. Do not place prompts, bearer tokens, or raw sensitive content in trace labels or alerts.
