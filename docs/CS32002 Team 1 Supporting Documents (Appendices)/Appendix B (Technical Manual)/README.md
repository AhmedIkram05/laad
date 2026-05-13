# Log Aggregation Analysis and Diagnostics Platform

Technical Manual for Running and Testing our Log Aggregration Analysis and Diagnostics System, Built for NCR Atleos.

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

From the repository root, use the Makefile to start all services:

```bash
make all      # Starts postgres, backend, generator, mlflow
make rebuild  # Full clean rebuild
```

The generator backfills 60 minutes of historical data on first boot, then enters live mode with probabilistic anomaly injection.

To train ML models:

```bash
make retrain              # Train on live generator data
make retrain-offline      # Train on offline dataset (all A1-A7 guaranteed)
make generate-training-data  # Generate 24h offline dataset (one-time setup)
```

### Running the API Server

The API server starts automatically with `make all`. API docs are available at <http://localhost:8000/docs>.

### Default Admin Account

Seeded automatically on first `python main.py` run, for development purposes:

- **Username:** admin
- **Password:** admin

### Running Tests

From the repository root run:

```bash
make pytest  # Runs all tests in Docker with isolated test DB
```

Current test status: **145/145 passing**.

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
