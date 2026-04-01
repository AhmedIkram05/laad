# Log Aggregation Analysis and Diagnostics Platform

User manual for running and testing the frontend and backend of the log aggregration, analysis and diagnostics system for NCR Atleos.

## Prerequisites

- Python 3.8+ (virtual environment recommended)
- Node.js (v16+ recommended) and `npm`
- `pip` for Python packages

## Backend (Python)

### Setup

From the repository root or the `backend` directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### Running the Pipeline

Initialises the database, generates 24h of synthetic data, and ingests all log sources into the database.

```bash
# Must be run from the backend directory
python main.py
```

### Running the API Server

Run the pipeline first to populate the database, then start the API server from the repo root:

```bash
# Must be run from the root directory
uvicorn backend.src.api.server:app --reload --port 8000
```

API docs: <http://localhost:8000/docs>

### Default Admin Account

Seeded automatically on first `python -m backend.main` for development purposes:

- **Username:** admin
- **Password:** admin

### Running Tests

From the repository root run:

```bash
pytest
```

Current test status: 39/39 passing.

## Frontend (React + Vite)

### Setup

```bash
cd frontend
npm install
```

### Development

```bash
npm run dev
```

The frontend development server runs via Vite (default port 5173). Open the app in your browser and ensure the backend API is running at <http://localhost:8000> for full functionality.
