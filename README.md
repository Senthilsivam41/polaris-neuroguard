# Polaris Neuro Guard 🧭🤖

> **A Neuro-Symbolic Multi-Agent Strategic Drift Guardrail for Strategic Decision-Making**

Polaris Neuro Guard is a strategic simulation platform built with Python and FastAPI. It models an enterprise initiative ("The Ship") steering toward a strategic objective ("The Mountain") through systemic constraints ("The Icebergs"). The platform calculates and prevents strategic drift under macro-environmental volatility using vector mechanics and deadlock detection.

## Milestone Achieved: Phases 1 to 8 Complete

Polaris Neuro Guard has achieved a major development milestone with the complete implementation, integration, and test verification of **Phases 1 through 8**:

1. **Phase 1: Core Simulation Mechanics**
   - 2D vector physics engine calculating steering intent vs. resultant trajectory.
   - Dynamic macro-environmental storms (Geopolitical, Meteorological, Economic).
   - Look-ahead capsule projection for systemic constraint collision detection (Icebergs).
   - Deterministic logical deadlock checking for opposing constraint pairs.

2. **Phase 2: Google ADK 2.0 Workflow Engine**
   - Four-node structured agent workflow (`goal_analyzer` → `constraint_predictor` → `weather_station` → `path_simulator`).
   - Unified typed state schema contract (`SimulationStateSchema`) with state transition safety checks.
   - Hermetic agent-to-agent (A2A) module interfaces.

3. **Phase 3: Strategic Drift Engine & Goal Contracts**
   - Immutable baseline and versioned `GoalContract` repository.
   - Natural-language change request drift analysis and extraction.
   - Multi-profile deterministic drift rules engine and semantic drift scoring.
   - Explicit human confirmation state machine for goal contract amendments ($vN \rightarrow vN+1$).

4. **Phase 4: HITL Interruptions, Checkpoints & Resume**
   - Typed real ADK workflow interruptions (`ADKInterruptionError`, `InterruptionReason`, `InterruptionPayload`).
   - Durable, atomic `CheckpointService` with optimistic version locking and secret scrubbing.
   - Authoritative `PausedSessionPolicy` guarding state integrity during interruptions (`HTTP 409 SIMULATION_PAUSED`).
   - Versioned simulation resume endpoint (`POST /api/v1/simulation/{sim_id}/resume`) with idempotency and trace correlation.

5. **Phase 5: Durable Persistence & Idempotency**
   - SQLite-backed `SQLiteWorkflowStore` replacing volatile process-local memory caches.
   - Atomic transactions with `BEGIN IMMEDIATE` serialize competing writes.
   - Optimistic concurrency control using autoincrementing version checks.
   - Scoped request idempotency for state mutation operations.

6. **Phase 6: API & Security Hardening**
   - Strict API/domain validation for vectors, icebergs, constraint and storm limits, plus explicit rejection of unknown storms.
   - Bearer-token authentication with simulation ownership enforcement and reviewer/override role support.
   - Authenticated A2A node apps, configured CORS origins, request-size limits, rate limiting, and request timeouts.
   - Append-only, hash-chained audit records with sensitive-field redaction for registrations, decisions, drift/amendment actions, storm injections, and HITL resumes.

7. **Phase 7: Observability & Operations**
   - Dependency-light Prometheus text metrics at `GET /metrics` and authenticated alert evaluation at `GET /api/v1/operations/alerts`.
   - Trace ID propagation via `X-Trace-Id` and workflow/node latency histograms.
   - Operator runbook in [docs/operations.md](docs/operations.md) covering panels, thresholds, and ownership.

8. **Phase 8: Evaluation & Quality Gates**
   - Versioned drift-benchmark corpus with ≥75% release accuracy gate.
   - Concurrent deterministic SLO checks (&lt;200ms), durable-store concurrency/replay, and audit hash-chain integrity tests.
   - CI quality workflow runs the Phase 8 suites on every push/PR.

## 🔄 Idempotency & Retry Policy

For mission-critical operations (`evaluate-decision` and `resume`), Polaris Neuro Guard implements robust idempotency controls:
- **Request Idempotency Key**: Scoped to the `request_id` or `resume_request_id` in the payload.
- **Duplicate Request Detection**:
  - If a duplicate request is received while the original is still running, the system returns `HTTP 409 Conflict` (`REQUEST_IN_PROGRESS`).
  - If the original request has completed, the system replays the cached response without re-executing the ADK workflow graph.
- **Payload Integrity**: If the same idempotency key is reused but with a different request payload, the system rejects it with `HTTP 409 Conflict` (`IDEMPOTENCY_KEY_REUSED`).

## 🏗️ Backend Layout

```text
├── README.md
├── requirements.txt
├── .gitignore
└── app/
    ├── __init__.py
    ├── main.py             # FastAPI entry point
    ├── core/
    │   ├── __init__.py
    │   └── config.py       # Configuration settings
    └── api/
        ├── __init__.py
        └── endpoints.py    # API Route Handlers
```

## 🚀 Getting Started

### 1. Set Up Environment
Create and activate a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Server

Configure a production API token and allowed frontend origins before starting the service. `POLARIS_API_TOKENS` maps each bearer token to its actor and roles:

```bash
export POLARIS_API_TOKENS='{"replace-with-a-secret-token":{"actor_id":"user_123","roles":["operator"]}}'
export ALLOWED_ORIGINS='https://app.example.com'
```

```bash
uvicorn app.main:app --reload
```
The server will start at `http://127.0.0.1:8000`. You can verify the setup by visiting `http://127.0.0.1:8000/health`.

Protected `/api/v1` and A2A operations require `Authorization: Bearer <token>`. For local offline/mock development only, set `OFFLINE_MODE=true` or `MOCK_MODE=true`; the development token is `dev-local-token`.

### Frontend cockpit

```bash
cd frontend && npm install && npm run dev
```

The Vite app proxies `/api` to `http://127.0.0.1:8000`. Onboarding accepts a Bearer token (defaults to `dev-local-token`). When a guardrail pauses the simulation, FractureModal calls `POST /resume` with the checkpoint metadata returned on the evaluate response. The right-rail **Goal Contract Amendment** panel submits change requests, runs drift evaluation, and confirms/rejects amendments.

### Security Controls

- `AUTH_REQUIRED` (default `true`) requires bearer-token authentication.
- `POLARIS_API_TOKENS` is a JSON object of tokens and principals; roles may include `operator`, `reviewer`, `override`, or `admin`.
- `ALLOWED_ORIGINS`, `RATE_LIMIT_PER_MINUTE`, `MAX_REQUEST_BYTES`, and `REQUEST_TIMEOUT_SECONDS` configure browser access and abuse protections.
- Security/audit failures use structured error codes; audit records are durable, append-only, hash chained, and redact token- and secret-like fields.

### 📖 API Interactive Documentation

Once the server is running, the interactive Swagger UI and ReDoc documentation are automatically published and accessible via:
* **Interactive Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) (View schemas, endpoints, and execute sample inputs directly in the browser)
* **ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc) (Clean, structured static documentation interface)

## 🪵 Ponytail Audit: Optimization Log

Following strict YAGNI and KISS principles, we audited the initial codebase and applied the following cleanups:
* **Modular Refactoring**: Removed the state-less `SimulationEngine` object wrapper and its `@staticmethod` annotations, converting the vector mathematics and execution logic into high-performance, module-level functions in [simulation.py](file:///Users/sendils/work/repo/adk-2_0/polaris-neuroguard/app/core/simulation.py).
* **Boilerplate Reduction**: Eliminated Pydantic `Settings` class wrapper in favor of plain static constants in [config.py](file:///Users/sendils/work/repo/adk-2_0/polaris-neuroguard/app/core/config.py) to save unnecessary object instantiations.
* **Payload Simplification**: Streamlined the Human-in-the-Loop (`hitl_interception_data`) reason-construction block in [endpoints.py](file:///Users/sendils/work/repo/adk-2_0/polaris-neuroguard/app/api/endpoints.py), removing intermediate variables and multiple string concatenation steps.
