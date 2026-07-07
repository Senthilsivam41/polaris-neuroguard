# Polaris Neuro Guard 🧭🤖

> **A Neuro-Symbolic Multi-Agent Simulation Framework Modeling Strategic Drift and Multi-Agent Guardrails Under Macro-Environmental Volatility.**

Polaris Neuro Guard is an advanced AI safety and strategic simulation platform built using **Google’s Agent Development Kit (ADK) 2.0** and **Antigravity**. It solves a critical vulnerability highlighted in recent arXiv literature: the systemic failure of traditional static guardrails when autonomous agents interact with human decision-makers in highly volatile, multi-constraint environments.

Using a compelling maritime navigation metaphor—where a CTO steers an enterprise initiative (The Ship) toward a strategic objective (The Mountain) through a field of self-blocking operational constraints (The Icebergs)—the system calculates and prevents **Strategic Drift** in real time.

---

## 🏗️ Core Architecture

Polaris Neuro Guard abandons brittle, monolithic sequential prompting in favor of a deterministic, cyclic **ADK 2.0 Graph Workflow**. The backend is powered by four specialized, concurrent agents interacting via the Agent-to-Agent (A2A) network protocol:

* **Goal Analyzer Agent (Codex Plus):** Translates high-level human user objectives into immutable mathematical constraints.
* **Environmental Weather Station Agent:** Ingests dynamic real-world macroeconomic and geopolitical triggers (e.g., supply chain shocks, resource hyper-inflation, regional conflicts) and translates them into physical vector forces acting upon the system.
* **Path Simulator Agent:** Employs **2D Vector Mechanics** to compute the actual track velocity and heading angle of the initiative, mapping exactly how environmental "winds" alter human intent.
* **Constraint Conflict Predictor Agent:** A symbolic logic engine that evaluates upcoming decisions for structural deadlocks (e.g., where selecting Option A introduces a constraint that inherently invalidates Option B), preventing silent cascading system failures.

---

## 🧮 The Mathematical Model

The engine models the "Cyber-Ocean" using classical vector addition to establish a mathematically verifiable delta between a human's intent and operational reality:

$$\vec{V}_g = \vec{V}_a + \vec{V}_s$$

Where:
* $\vec{V}_a$ is the **Intent Vector** (The CTO's strategic direction and velocity).
* $\vec{V}_s$ is the **Environmental Storm Vector** (The compounding displacement forces of external real-world shocks).
* $\vec{V}_g$ is the **Resultant Vector** (The actual physical trajectory of the project).

When the angular drift delta or a 3-turn trajectory look-ahead predicts an imminent intersection with a constraint boundary (Iceberg), the system invokes native **ADK 2.0 Human-in-the-Loop (HITL)** primitives. It pauses execution, preserves graph memory state, and pushes a telemetry payload to the visual dashboard for strategic remediation.
