# Polaris Neuro Guard 🧭🤖

> **A Neuro-Symbolic Multi-Agent Strategic Drift Guardrail for CTO Decision-Making**

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
