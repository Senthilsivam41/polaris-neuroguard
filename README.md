# Polaris Neuro Guard 🧭🤖

> **A Neuro-Symbolic Multi-Agent Strategic Drift Guardrail for Strategic Decision-Making**

Polaris Neuro Guard is a strategic simulation platform built with Python and FastAPI. It models an enterprise initiative ("The Ship") steering toward a strategic objective ("The Mountain") through systemic constraints ("The Icebergs"). The platform calculates and prevents strategic drift under macro-environmental volatility using vector mechanics and deadlock detection.

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
```bash
uvicorn app.main:app --reload
```
The server will start at `http://127.0.0.1:8000`. You can verify the setup by visiting `http://127.0.0.1:8000/health`.

### 📖 API Interactive Documentation

Once the server is running, the interactive Swagger UI and ReDoc documentation are automatically published and accessible via:
* **Interactive Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) (View schemas, endpoints, and execute sample inputs directly in the browser)
* **ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc) (Clean, structured static documentation interface)

## 🪵 Ponytail Audit: Optimization Log

Following strict YAGNI and KISS principles, we audited the initial codebase and applied the following cleanups:
* **Modular Refactoring**: Removed the state-less `SimulationEngine` object wrapper and its `@staticmethod` annotations, converting the vector mathematics and execution logic into high-performance, module-level functions in [simulation.py](file:///Users/sendils/work/repo/adk-2_0/polaris-neuroguard/app/core/simulation.py).
* **Boilerplate Reduction**: Eliminated Pydantic `Settings` class wrapper in favor of plain static constants in [config.py](file:///Users/sendils/work/repo/adk-2_0/polaris-neuroguard/app/core/config.py) to save unnecessary object instantiations.
* **Payload Simplification**: Streamlined the Human-in-the-Loop (`hitl_interception_data`) reason-construction block in [endpoints.py](file:///Users/sendils/work/repo/adk-2_0/polaris-neuroguard/app/api/endpoints.py), removing intermediate variables and multiple string concatenation steps.
