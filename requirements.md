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
  | **Constraint Conflict Predictor Agent** | `LlmAgent` (with `FunctionTool` sub-call to `check_logical_deadlocks` for static pairs) | Runs SMT symbolic checks, then reasons over *novel* constraint phrasings that static pair lists would fail to catch. |

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
* **FR-3.5:** The four nodes must be independently exposable via A2A (`google.adk.a2a.to_a2a(agent)`), enabling swapping of local nodes for remote agents.

### 2.4 Mathematical Drift & Trajectory Calculations
* **FR-4.1:** The system must compute the actual trajectory using 2D vector mechanics, executing vector addition of human strategic intent ($\vec{V}_a$) and environmental storm displacement ($\vec{V}_s$):

$$\vec{V}_g = \vec{V}_a + \vec{V}_s$$

* **FR-4.2:** The system must extract the absolute angular difference—the Strategic Drift Delta ($\sigma$)—between the intended heading ($\theta_a$) and the actual resultant tracking angle ($\theta_g$):

$$\sigma = |\theta_g - \theta_a|$$

* **FR-4.3:** The engine must flag an active drift state whenever the delta angle ($\sigma$) exceeds a configuration threshold of $15^\circ$.

### 2.5 SMT Constraint Verification & Human-in-the-Loop (HITL) Interception
* **FR-5.1:** The Constraint Conflict Predictor must flag an immediate system deadlock if a user introduces mutually exclusive parameter configurations (e.g., setting a `RIGID_TIMELINE` boundary while simultaneously declaring a `FREEZE_HEADCOUNT` constraint during a storm event).
* **FR-5.2:** If a logical deadlock is detected, the engine must immediately drop the effective intent velocity magnitude ($v_a$) to $0$, representing an engine stall, while allowing environmental vectors to continue displacing the coordinates.
* **FR-5.3:** The system must calculate a 3-turn forward trajectory projection. If the look-ahead coordinates fall within the danger radius ($R$) of a pre-configured constraint obstacle (Iceberg), the Path Simulator node **must** raise `NodeInterruptedError` to intercept progress.
* **FR-5.4:** On `NodeInterruptedError`:
  1. The ADK 2.0 runtime must automatically persist the graph's session state (current node, position, burn rate, deadlock/collision context).
  2. The API layer must expose a separate resume endpoint `POST /simulation/{simulation_id}/resume` that accepts a human decision payload and re-enters the graph at the paused node. `POST /simulation/evaluate-decision` must be blocked and return a paused state if invoked while the simulation is interrupted.
  3. The structured JSON payload returned at pause time must contain `reason` and `telemetry_snapshot` diagnostic states.

---

## 3. Non-Functional Requirements

### 3.1 Performance & Latency
* **NFR-1.1:** The backend API must process a single evaluation turn—including vector addition, lookup checks, and collision projections—in less than 200ms under standard execution conditions.
* **NFR-1.2:** All four graph nodes must be `to_a2a`-exposable, and execution under a local co-located graph and an A2A-swapped remote node configuration must yield identical telemetry output.

### 3.2 Extensibility & Architecture Constraints
* **NFR-2.1:** The system code must follow a strict modular design pattern to seamlessly integrate with frontend canvas wrappers without modifying the underlying vector logic.
* **NFR-2.2:** The architecture must strictly honor YAGNI (You Ain't Gonna Need It) principles, eliminating bloated boilerplate code in favor of native Python libraries and FastAPI dependencies.

### 3.3 Data Management
* **NFR-3.1:** Session tokens, telemetry tracking, and active constraint matrices must be managed via an isolated, lightweight, thread-safe in-memory data store to maximize processing speed.

---

## 4. Technical Stack Requirements

* **Language Runtime:** Python 3.11+
* **Framework Core:** `google-adk` package pinned with compatible-release operator against 2.0 (e.g., `google-adk[a2a]~=2.0`).
* **API Framework:** FastAPI with Pydantic v2 validation components.
* **AI Core Models:** Gemini 2.x family models for LLM-based agent nodes.
* **Mathematical Operations:** Native Python `math` module (vector coordinate mapping, geometric parsing).