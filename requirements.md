# Requirements Specification: Polaris Neuro Guard 🧭🤖

This document outlines the functional, non-functional, and technical requirements for **Polaris Neuro Guard**, a neuro-symbolic multi-agent simulation framework designed to model and mitigate strategic drift under macro-environmental volatility.

---

## 1. Project Overview & Objectives
The goal of Polaris Neuro Guard is to provide an enterprise-grade simulation engine that monitors human strategic decisions against shifting external constraints. By combining generative AI capabilities with strict mathematical validation, the system flags when a user's choices drift away from their primary objectives or create systemic deadlocks.

### Core Metaphor Mapping
* **The Ship (The Initiative):** Represents the corporate project or technical roadmap being executed.
* **The Destination (The Mountain):** The immutable anchor goal set by the user.
* **The Weather (The Environment):** Real-world geopolitical, environmental, and economic disruptions.
* **The Icebergs (The Constraints):** Structural, self-blocking rules that cause system crashes or deadlocks.

---

## 2. Functional Requirements

### 2.1 User Onboarding & Profile Management
* **FR-1.1:** The system must provide an API endpoint to ingest and register user profiles, establishing the operational baseline.
* **FR-1.2:** The profile intake payload must enforce validation for the following parameters using Pydantic v2:
  * `user_id`: Unique identifier for the session.
  * `role`: User organizational title (e.g., Chief Technology Officer).
  * `industry`: Market sector context (e.g., Fintech, Healthcare).
  * `anchor_goal`: An object defining the ultimate target destination, containing:
    * `title`: Description of the goal.
    * `target_timeline_months`: Integer constraint.
    * `budget_limit_usd`: Float constraint.
    * `reliability_target_sla`: Float metric (e.g., 99.99).
  * `risk_tolerance`: Enumerated value (`Conservative`, `Balanced`, `Aggressive`).
* **FR-1.3:** Upon successful registration, the engine must initialize a dedicated simulation session with fixed terminal coordinates representing the goal destination, mapped on a 2D plane at coordinate $(0, 1000)$.

### 2.2 Environmental Shock & Weather Injection Engine
* **FR-2.1:** The system must support the injection of dynamic macro-environmental modifiers that act as vector forces against the simulation state.
* **FR-2.2:** The system must natively support three pre-configured real-world disaster profiles:
  * **Geopolitical Conflict (e.g., Israel-Iraq Escalation):** Modeled as a pure headwind vector acting directly against forward progress.
  * **Natural Disaster (e.g., Category 4 Cyclone):** Modeled as a severe lateral crosswind vector introducing physical deviation.
  * **Macroeconomic Shock (e.g., Surging Petrol Prices):** Modeled as a financial friction scalar that multiplies operational burn-rates.

### 2.3 Multi-Agent Simulation Core (ADK 2.0 Graph Workflow)
* **FR-3.1:** The simulation loop **must** be constructed as a `WorkflowAgent` graph (`google.adk.agents.WorkflowAgent`). Direct function-to-function calls between the four domains below are **not permitted** — each domain must be a distinct graph node reachable only via a defined edge.
* **FR-3.2:** The graph must contain exactly four nodes, each independently unit-testable in isolation from the graph:

  | Node | ADK primitive | Responsibility |
  |---|---|---|
  | **Goal Analyzer Agent** | `LlmAgent` | Evaluates the user's declared intent vector against the registered `anchor_goal` and `risk_tolerance`. Produces a qualitative assessment that can flag intent that is strategically inconsistent with the stated goal (e.g. burning budget headroom to preserve heading). |
  | **Environmental Weather Station Agent** | `FunctionTool` wrapping `calculate_resultant_vector` | Deterministic — applies active storm vectors. Stays a pure function/tool. |
  | **Path Simulator Agent** | `FunctionTool` wrapping `execute_turn` position/burn-rate math | Deterministic — advances coordinates, computes burn rate, and executes look-ahead checks. |
  | **Constraint Conflict Predictor Agent** | `LlmAgent` (with `FunctionTool` sub-call to `check_logical_deadlocks` for static pairs) | Runs deterministic opposing-pair checks, then reasons over *novel* constraint phrasings that static pair lists would fail to catch. |

* **FR-3.3:** Edges must route as follows, matching the intended data dependency flow:
  ```
  ("start", "GoalAnalyzer")
  ("GoalAnalyzer", "ConstraintPredictor")
  ("ConstraintPredictor", "WeatherStation", "no_deadlock")
  ("ConstraintPredictor", "PathSimulator", "deadlock")   # zero-velocity path per FR-5.2
  ("WeatherStation", "PathSimulator")
  ("PathSimulator", "end")
  ```
* **FR-3.4:** Each node must define a `RetryConfig` (e.g., `RetryConfig(max_attempts=3)`), and node implementations must **not** catch bare `Exception` or `BaseException` internally. All exceptions must propagate up to the framework to allow automatic retries and HITL interruptions to function correctly.
* **FR-3.5:** The two LLM nodes (`goal_analyzer`, `constraint_predictor`) and the `simulation_workflow` must be independently exposable via A2A (`google.adk.a2a.to_a2a(...)`). Deterministic FunctionNodes (`weather_station`, `path_simulator`) remain local graph nodes; NFR-1.2 requires their telemetry to match across an A2A-style serialization swap harness (and live remote swap when available).

### 2.4 Mathematical Drift & Trajectory Calculations
* **FR-4.1:** The system must compute the actual trajectory using 2D vector mechanics, executing vector addition of human strategic intent ($\vec{V}_a$) and environmental storm displacement ($\vec{V}_s$):

$$\vec{V}_g = \vec{V}_a + \vec{V}_s$$

* **FR-4.2:** The system must extract the absolute angular difference—the Strategic Drift Delta ($\sigma$)—between the intended heading ($\theta_a$) and the actual resultant tracking angle ($\theta_g$):

$$\sigma = |\theta_g - \theta_a|$$

* **FR-4.3:** The engine must flag an active drift state whenever the delta angle ($\sigma$) exceeds a configuration threshold of $15^\circ$.

### 2.5 Constraint Conflict Verification & Human-in-the-Loop (HITL) Interception
* **FR-5.1:** The Constraint Conflict Predictor must flag an immediate system deadlock if a user introduces mutually exclusive parameter configurations (e.g., setting a `RIGID_TIMELINE` boundary while simultaneously declaring a `FREEZE_HEADCOUNT` constraint during a storm event). Verification is **neuro-symbolic**: a deterministic static opposing-pair checker covers known constraint pairs, and an `LlmAgent` reasons over novel phrasings that the static list would miss. A full SMT solver (e.g. Z3) is **out of scope** for this release; requirements that previously said "SMT" refer to this pair+LLM conflict layer.
* **FR-5.2:** If a logical deadlock is detected, the engine must immediately drop the effective intent velocity magnitude ($v_a$) to $0$, representing an engine stall, while allowing environmental vectors to continue displacing the coordinates.
* **FR-5.3:** The system must calculate a 3-turn forward trajectory projection. If the look-ahead coordinates fall within the danger radius ($R$) of a pre-configured constraint obstacle (Iceberg), the Path Simulator node **must** raise `NodeInterruptedError` to intercept progress.
* **FR-5.4:** On `NodeInterruptedError`:
  1. The ADK 2.0 runtime must automatically persist the graph's session state (current node, position, burn rate, deadlock/collision context).
  2. The API layer must expose a separate resume endpoint `POST /simulation/{simulation_id}/resume` that accepts a human decision payload and re-enters the graph at the paused node. `POST /simulation/evaluate-decision` must be blocked and return a paused state if invoked while the simulation is interrupted.
  3. The structured JSON payload returned at pause time must contain `reason`, `telemetry_snapshot`, and when available `checkpoint_id` / `checkpoint_version` for resume.

### 2.6 API Security, Authorization & Auditability
* **FR-6.1:** Protected API and A2A operations must require bearer-token authentication. Production deployments must configure tokens through `POLARIS_API_TOKENS`; offline/mock mode may provide an explicitly documented development token.
* **FR-6.2:** The system must enforce simulation ownership for state reads and mutations. A caller may access only simulations owned by its authenticated actor unless it has an authorized `reviewer`, `override`, or `admin` role.
* **FR-6.3:** Domain/API validation must reject invalid vector headings and magnitudes, non-positive iceberg radii, excessive constraint/storm/iceberg counts, and unknown storm names. Validation failures must return structured client errors and must not mutate session state.
* **FR-6.4:** Browser access must use configured CORS origins only. The API must enforce configurable request-size limits, per-client rate limits, and request execution timeouts; rate-limit and timeout failures must be observable through structured responses/logging.
* **FR-6.5:** The system must record security-relevant and workflow actions in a durable append-only audit log, including baseline goal hashes, state-changing decisions, change/drift evidence, amendment decisions, storm injection, and HITL resumes. Audit entries must identify actor and request where available, redact sensitive fields, and be hash chained to make modification evident.
* **FR-6.6:** A2A-exposed agent applications must apply the same authentication policy as the primary REST API.

---

## 3. Non-Functional Requirements

### 3.1 Performance & Latency
* **NFR-1.1:** The backend API must process a single evaluation turn—including vector addition, lookup checks, and collision projections—in less than 200ms under standard execution conditions.
* **NFR-1.2:** All four graph nodes must be `to_a2a`-exposable. Deterministic nodes (`weather_station`, `path_simulator`) must yield identical telemetry under a local co-located invocation and an A2A-swapped boundary that round-trips the same inputs (serialization hop or remote agent). Live multi-process remote parity is validated when the optional `a2a` SDK is present; otherwise an in-process swap harness is the release gate.

### 3.2 Extensibility & Architecture Constraints
* **NFR-2.1:** The system code must follow a strict modular design pattern to seamlessly integrate with frontend canvas wrappers without modifying the underlying vector logic.
* **NFR-2.2:** The architecture must strictly honor YAGNI (You Ain't Gonna Need It) principles, eliminating bloated boilerplate code in favor of native Python libraries and FastAPI dependencies.

### 3.3 Data Management
* **NFR-3.1:** Simulation sessions, telemetry tracking, active constraint matrices, idempotency records, and audit records must be managed by an isolated lightweight durable store. State updates must use atomic transactions and optimistic concurrency controls; in-memory structures may be used only as non-authoritative process-local caches.

### 3.4 Security & Operational Resilience
* **NFR-4.1:** Authentication must fail closed when enabled: missing, malformed, or unknown bearer tokens must not grant access.
* **NFR-4.2:** Secrets, tokens, passwords, and API keys must not be emitted in audit records or application logs.
* **NFR-4.3:** Security limits—including CORS origins, rate limit, maximum request size, and request timeout—must be configurable by environment without code changes.

---

## 4. Technical Stack Requirements

* **Language Runtime:** Python 3.11+
* **Framework Core:** `google-adk` package pinned with compatible-release operator against 2.0 (e.g., `google-adk[a2a]~=2.0`).
* **API Framework:** FastAPI with Pydantic v2 validation components.
* **AI Core Models:** Gemini 2.x family models for LLM-based agent nodes.
* **Mathematical Operations:** Native Python `math` module (vector coordinate mapping, geometric parsing).
