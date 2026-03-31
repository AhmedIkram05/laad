# Backend — NCR Atleos Log Aggregation Platform

## Setup (if needed?)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

## Running the Pipeline

Initialises the database, generates 24h of synthetic data, and ingests all 7 log sources:

```bash
# Must be ran from backend directory
python main.py
```

## Running the API Server

Run the pipeline first to populate the database, then:

```bash
#Must be ran from root directory
uvicorn backend.src.api.server:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs`.

## Default Admin Account

Seeded automatically on first `python -m backend.main` for dev purposes:

- **Username:** `admin`
- **Password:** `admin`

Change this after first login.

## Running Tests (from root)

```bash
pytest
```

Current status: **34/34 passing.**
