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
* **FR-3.1:** The simulation loop must be orchestrated as a cyclic graph workflow using Google Agent Development Kit (ADK) 2.0 primitives.
* **FR-3.2:** State execution must be distributed among four specialized backend agent nodes interacting via the Agent-to-Agent (A2A) network protocol:
  * **Goal Analyzer Agent:** Evaluates human inputs against the profile boundary configurations.
  * **Environmental Weather Station Agent:** Dynamically applies vector offsets based on active environmental shock factors.
  * **Path Simulator Agent:** Computes spatial coordinates using 2D vector mathematics.
  * **Constraint Conflict Predictor Agent:** Synthesizes symbolic logical rules to check for contradictory, self-blocking operational constraints.

### 2.4 Mathematical Drift & Trajectory Calculations
* **FR-4.1:** The system must compute the actual trajectory using 2D vector mechanics, executing vector addition of human strategic intent ($\vec{V}_a$) and environmental storm displacement ($\vec{V}_s$):

$$\vec{V}_g = \vec{V}_a + \vec{V}_s$$

* **FR-4.2:** The system must extract the absolute angular difference—the Strategic Drift Delta ($\sigma$)—between the intended heading ($\theta_a$) and the actual resultant tracking angle ($\theta_g$):

$$\sigma = |\theta_g - \theta_a|$$

* **FR-4.3:** The engine must flag an active drift state whenever the delta angle ($\sigma$) exceeds a configuration threshold of $15^\circ$.

### 2.5 SMT Constraint Verification & Human-in-the-Loop (HITL) Interception
* **FR-5.1:** The Constraint Conflict Predictor must flag an immediate system deadlock if a user introduces mutually exclusive parameter configurations (e.g., setting a `RIGID_TIMELINE` boundary while simultaneously declaring a `FREEZE_HEADCOUNT` constraint during a storm event).
* **FR-5.2:** If a logical deadlock is detected, the engine must immediately drop the effective intent velocity magnitude ($v_a$) to $0$, representing an engine stall, while allowing environmental vectors to continue displacing the coordinates.
* **FR-5.3:** The system must calculate a 3-turn forward trajectory projection. If the look-ahead coordinates fall within the danger radius ($R$) of a pre-configured constraint obstacle (Iceberg), the system must execute an ADK 2.0 native Human-in-the-Loop intercept.
* **FR-5.4:** The HITL trigger must pause graph execution, preserve memory state, block auto-progression, and yield a structured JSON analysis payload detailing the precise mathematical contradiction for user remediation.

---

## 3. Non-Functional Requirements

### 3.1 Performance & Latency
* **NFR-1.1:** The backend API must process a single evaluation turn—including vector addition, lookup checks, and collision projections—in less than 200ms under standard execution conditions.
* **NFR-1.2:** Agent-to-Agent graph state synchronization via ADK 2.0 must maintain low-latency thread safety within the local execution environment.

### 3.2 Extensibility & Architecture Constraints
* **NFR-2.1:** The system code must follow a strict modular design pattern to seamlessly integrate with frontend canvas wrappers (Three.js or React Flow) without modifying the underlying vector logic.
* **NFR-2.2:** The architecture must strictly honor YAGNI (You Ain't Gonna Need It) principles, eliminating bloated boilerplate code in favor of native Python libraries and FastAPI dependencies.

### 3.3 Data Management
* **NFR-3.1:** Session tokens, telemetry tracking, and active constraint matrices must be managed via an isolated, lightweight, thread-safe in-memory data store to maximize processing speed.

---

## 4. Technical Stack Requirements

* **Language Runtime:** Python 3.11+
* **Framework Core:** Google Agent Development Kit (ADK) 2.0 Stable Release
* **Development Environment:** Antigravity CLI Tooling (`agents-cli`)
* **AI Core Models:** Codex Plus Integration Layer
* **API Framework:** FastAPI with Pydantic v2 validation components
* **Mathematical Operations:** Native Python `math` module (vector coordinate mapping, geometric parsing)