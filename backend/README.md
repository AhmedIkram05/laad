# NCR Atleos Log Aggregation, Analysis & Diagnostics Platform - Backend

## Quick Start (Running the Pipeline)

The central orchestrator script is `backend/main.py`. It handles initialising the database, generating a full 24-hour synthetic dataset, and concurrently ingesting all 7 log sources.

Run from the repository root, you may need to install a python virtual environment, you will definitely need to install the requirements in **backend/requirements.txt**:

### Initialise Virtual Environment (Optional)

```bash
python -m venv .venv
source .venv/bin/activate
```

### Install Backend Requirements

```bash
pip install -r backend/requirements.txt
```

### Run Backend Pipeline: Database init, Custom logs generator, Log ingestion

```bash
python -m backend.main
```

### What `main.py` actually does

1. **Initialises Database:** Creates `database.db` and applies the 5-table "Lean Data Lake" schema in `schema.sql`. It also seeds reference data (like ATMs).
2. **Generates Data:** Invokes the synthetic data generator to create 24 hours of simulated logs in `custom_synthetic_data_sources/`. It uses a **scripted scenario-injection model (A1–A7)** to ensure realistic cross-source correlation.
3. **Ingests Data:** Runs multi-threaded ingestion using `ThreadPoolExecutor` to process all 7 sources concurrently into the SQLite database. High-concurrency is supported via **WAL mode**, ensuring no record is lost during the burst.

## Generator Configuration

The generator is now primarily driven by the **A1–A7 Anomaly Scenarios** defined in the project brief. To tweak the baseline duration, edit the constants in `backend/ingestion/custom_data_generator.py`:

- `HOURS` (Default `24`): The total time span of the generated data.
- **Deterministic Scenarios**: All anomalies (A1–A7) are injected with shared `correlation_id` keys across logs and metrics to enable immediate cross-source analysis.
- **DLQ Testing (A7)**: The generator automatically injects 3 specific malformations (2 Kafka nulls/out-of-order, 1 Prometheus non-numeric) to verify the robustness of the Dead-Letter Queue.

## Database Architecture ("Lean Schema")

The database utilises a highly optimised 5-table strategy to minimise ingestion overhead while maintaining rapid query capabilities for the frontend.

- **`events`**: Unified store for all discrete logs (ATM App, Hardware, Terminal Handler).
- **`metrics`**: Unified store for all continuous metric streams (Windows OS, Prometheus, GCP Cloud, Kafka).
- **`atms`**: Reference table mapping `atm_id` to its `os_version` and location.
- **`anomalies`**: Destination table for the Detection Engine's findings (includes embedded recommendations).
- **`ingestion_errors`**: The "Dead Letter Queue" (DLQ). Catches strictly malformed records to prevent pipeline crashes.

### Frontend Views

To simplify reading data from the `events` and `metrics` tables (which utilize JSON payload columns), three flattened views are provided:

- `v_events_flat`
- `v_metrics_flat`
- `v_unified_analysis` (Provides a normalised timeline combining events and metrics for the dashboard).

## Testing

The codebase includes a full `unittest` and `pytest` compatible suite to verify schema compliance, concurrent ingestion resilience, and parser error handling.

To run the tests, execute from the repository root:

```bash
pytest backend/tests/ -v
# or simply 'pytest', should work
```

### Note on test data

The test suite uses a small, deterministic dataset that is generated automatically by the pytest session fixture. Tests expect the generated dataset (exposed via the `TEST_DATA_DIR` environment variable) and no longer use the Sample-Assets sources. If `TEST_DATA_DIR` is not present the tests will raise an error — run `pytest` normally to have the fixture create the dataset.
