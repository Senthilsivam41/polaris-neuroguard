# Phase 7 Operations Runbook

## Signals and dashboard panels

Scrape `GET /metrics` with Prometheus. Build environment-separated dashboards using the deployment/environment label supplied by the scraper configuration.

- API latency: `polaris_api_request_seconds` p50, p95, and p99.
- Workflow latency: `polaris_workflow_seconds` p50, p95, and p99.
- Reliability: `polaris_workflow_executions_total`, `polaris_api_timeouts_total`, and HTTP status-labelled request counts.
- Decision quality: `polaris_drift_warnings_total` and `polaris_hitl_interruptions_total`.
- Recovery: `polaris_workflow_resumes_total` by outcome.

## Alerts and ownership

| Alert | Threshold | Owner | Recovery |
|---|---:|---|---|
| Workflow failure | Any failure | platform-oncall | Inspect trace ID, ADK logs, then retry with the same idempotency key only after resolving the root cause. |
| High latency | workflow/API p95 > 2 s | platform-oncall | Check Gemini/A2A availability, request volume, and retry counts; scale or disable affected remote node. |
| Version conflicts | >=5 observed conflicts | platform-oncall | Check duplicate clients and retry behavior; retain the winning durable session version. |
| Stuck interruptions | >=5 interruptions | workflow-owner | Review checkpoint reason and apply an authorized resume or amendment decision. |
| Drift spike | sustained warning increase | product-owner | Review active storms, constraints, and false-positive overrides. |

`GET /api/v1/operations/alerts` exposes the in-process threshold evaluation for authenticated operators. Production alert routing should page the listed owner through the deployment's alert manager.

## Trace handling

Clients may provide `X-Trace-Id`; otherwise the API creates one and returns it in the response header. Include it when escalating an incident. Do not place prompts, bearer tokens, or raw sensitive content in trace labels or alerts.
