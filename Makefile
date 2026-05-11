.PHONY: help
help:
	@echo "LAAD — Available commands"
	@echo ""
	@echo "  make start         Start everything (postgres + backend + generator + mlflow)"
	@echo "  make stop          Stop all services"
	@echo ""
	@echo "Database:"
	@echo "  make db-up          Start PostgreSQL (port 5432)"
	@echo "  make db-down        Stop PostgreSQL"
	@echo "  make db-logs        Tail PostgreSQL logs"
	@echo "  make db-reset       Wipe and recreate PostgreSQL"
	@echo ""
	@echo "Services:"
	@echo "  make up             Start postgres + backend"
	@echo "  make down           Stop all services"
	@echo ""
	@echo "Generator:"
	@echo "  make generator-up    Start generator container"
	@echo "  make generator-logs  Tail generator logs"
	@echo "  make generator-down  Stop generator"
	@echo ""
	@echo "ML:"
	@echo "  make ml-up          Start MLflow UI (port 5000)"
	@echo "  make ml-logs        Tail MLflow logs"
	@echo "  make ml-down        Stop MLflow"
	@echo "  make train          Run ML training pipeline"
	@echo ""
	@echo "Development:"
	@echo "  make test           Run full test suite"
	@echo "  make test-db-up     Start test DB (port 5433)"
	@echo "  make test-db-down   Stop test DB"
	@echo "  make server         Run backend API locally"
	@echo "  make generate       Run generator locally"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          Stop all containers and remove volumes"

# ── One-command start/stop ───────────────────────────────────────────────────

start:
	docker compose up -d postgres backend generator
	@echo "postgres + backend + generator started."
	@echo "  Backend API:   http://localhost:8000"
	@echo "  PostgreSQL:    localhost:5432"
	@echo "  MLflow:        make ml-up (starts on demand)"

stop:
	docker compose stop

# ── Database ──────────────────────────────────────────────────────────────────

db-up:
	docker compose up -d postgres
	@echo "PostgreSQL started on localhost:5432"

db-down:
	docker compose stop postgres

db-logs:
	docker compose logs -f postgres

db-reset:
	docker compose down -v
	docker compose up -d postgres
	@echo "PostgreSQL reset (schema re-initialised from schema.sql)"

# ── Services ──────────────────────────────────────────────────────────────────

up:
	docker compose up -d postgres backend
	@echo "postgres + backend running. Generator: make generator-up | MLflow: make ml-up"

up-full:
	docker compose up -d postgres backend generator
	@echo "postgres + backend + generator running (profiles disabled, all active)"

down:
	docker compose down

# ── Generator ─────────────────────────────────────────────────────────────────

generator-up:
	docker compose --profile generator up -d
	@echo "Generator started (use 'make generator-logs' to watch)"

generator-logs:
	docker compose logs -f generator

generator-down:
	docker compose stop generator

# ── ML ───────────────────────────────────────────────────────────────────────

ml-up:
	docker compose --profile ml up -d
	@echo "MLflow UI available at http://localhost:5000"

ml-logs:
	docker compose logs -f mlflow

ml-down:
	docker compose stop mlflow

train:
	docker compose exec backend python -m backend.src.anomaly_detection.ml.train

# ── Development ────────────────────────────────────────────────────────────────

test-db-up:
	docker compose -f docker-compose.test.yml up -d
	@echo "Test database started on localhost:5433"

test-db-down:
	docker compose -f docker-compose.test.yml down

test: test-db-up
	pytest backend/tests/ -q

server:
	python -m uvicorn backend.src.api.server:app --reload --port 8000

generate:
	python -m backend.generator.continuous_generator

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	docker compose down -v
	docker compose -f docker-compose.test.yml down -v
	@echo "All containers and volumes removed"