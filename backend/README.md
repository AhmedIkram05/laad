# Backend, Database & Their Tests

This repository contains ingestion parsers, SQLite helpers, and a lightweight test
suite used to validate concurrent writes and schema correctness.

## Key locations

- Parsers and base classes: [ingestion/parsers](ingestion/parsers/__init__.py#L1)
- Resilient writer helper (helps with concurrent writes in SQLite): [ingestion/write_helper.py](ingestion/write_helper.py#L1)
- Centralised DB connection (PRAGMA tuned): [database/connection.py](database/connection.py#L1)
- Schema and seeds: [database/schema.sql](database/schema.sql#L1) and [database/init_db.py](database/init_db.py#L1)
- Tests: [tests/](tests) including concurrency smoke test and schema verification

## Developer setup & running

Follow these steps to create a development virtual environment, initialise the real database, and run the test suite.

1. You may need to create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

1. Install test/runtime dependencies:

```bash
pip install -r backend/requirements.txt
```

1. Initialise the real (development) database and seed templates (run from the repo root):

```bash
python -m backend.database.init_db
# or (if you want to run the file directly):
PYTHONPATH=. python3 backend/database/init_db.py
```

This creates the database at `backend/database/database.db` by default and applies the canonical schema in `backend/database/schema.sql`.

1. Run the test suite from the repository root:

```bash
pytest -q
```

## Architecture (summary)

- **DB connection:** centralised `get_db()` in `database/connection.py` that applies SQLite PRAGMAs (WAL, busy timeout, foreign keys, etc.) to improve concurrent-writing behavior.
- **Resilient writer:** `ingestion/write_helper.py` exposes `write_batch()` which performs transactional batched inserts with retries and exponential backoff on transient locks.
- **Parsers:** parser classes under `ingestion/parsers/` buffer rows, serialize variable fields into a `payload` JSON column, and call `write_batch()` to persist data.
- **Tests:** unittest-based suite in `tests/` includes a concurrency smoke test and a DB schema verification test to validate correctness under contention.
