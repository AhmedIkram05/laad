.PHONY: help all rebuild rebuild-backend clean logs retrain pytest

help:
	@echo "LAAD Makefile — Essential commands"
	@echo ""
	@echo "  make all          Start all services (postgres, backend, generator, mlflow)"
	@echo "  make rebuild      Full rebuild: remove ALL containers/volumes/images, then start fresh"
	@echo "  make rebuild-backend  Rebuild backend image only, keep other services running"
	@echo "  make clean       Stop all containers and remove volumes"
	@echo "  make logs        Follow all service logs"
	@echo "  make retrain     Retrain ML models (Isolation Forest + XGBoost)"
	@echo "  make pytest      Run all tests in Docker (postgres_test + pytest containers)"
	@echo ""
	@echo "Services:"
	@echo "  Backend API:     http://localhost:8000"
	@echo "  PostgreSQL:      localhost:5432"
	@echo "  Test DB:         localhost:5433"
	@echo "  MLflow UI:       http://localhost:5001"

# ── Start All ────────────────────────────────────────────────────────────────

all:
	docker compose up -d --build postgres backend generator
	docker compose --profile ml up -d
	@echo ""
	@echo "✓ All services started!"
	@echo "  Backend API:     http://localhost:8000"
	@echo "  PostgreSQL:      localhost:5432"
	@echo "  Test DB:         localhost:5433"
	@echo "  MLflow UI:       http://localhost:5001"
	@echo ""

# ── Full Rebuild ────────────────────────────────────────────────────────────

rebuild:
	@echo "==> Stopping all containers..."
	-docker compose --profile ml down -v
	-docker compose --profile test down -v
	-docker compose --profile generator down -v
	-docker compose down -v
	@echo "==> Removing orphaned containers..."
	-docker compose down --remove-orphans
	@echo "==> Removing LAAD volumes..."
	-docker volume rm laad_postgres_data laad_mlflow_artifacts laad_postgres_test_data 2>/dev/null; true
	@echo "==> Removing LAAD images..."
	-docker rmi laad-backend:latest laad-generator:latest 2>/dev/null; true
	@echo "==> Starting fresh..."
	docker compose up -d --build postgres backend generator
	docker compose --profile ml up -d
	@echo ""
	@echo "✓ Rebuild complete!"
	@echo "  Backend API:     http://localhost:8000"
	@echo "  PostgreSQL:      localhost:5432"
	@echo "  Test DB:         localhost:5433"
	@echo "  MLflow UI:       http://localhost:5001"
	@echo ""

# ── Backend-only Rebuild ───────────────────────────────────────────────────

rebuild-backend:
	docker compose build backend
	docker compose up -d --no-deps backend
	@echo "✓ Backend image rebuilt and container restarted"

# ── Stop All ─────────────────────────────────────────────────────────────

clean:
	-docker compose --profile ml down -v
	-docker compose --profile test down -v
	-docker compose --profile generator down -v
	-docker compose down -v
	-docker compose down --remove-orphans
	@echo "✓ All services stopped and volumes removed"

# ── Follow Logs ─────────────────────────────────────────────────────────────

logs:
	docker compose logs -f

# ── Retrain ML Models ──────────────────────────────────────────────────────

retrain:
	@echo "==> Retraining ML models..."
	docker compose exec backend python -m backend.src.anomaly_detection.ml.train
	@echo ""
	@echo "✓ Retrain complete!"
	@echo "  View training run at: http://localhost:5001"

# ── Run Tests ──────────────────────────────────────────────────────────────

pytest:
	@echo "==> Running tests (assumes main services are already running)..."
	docker compose --profile test run --rm pytest
	@echo "==> Stopping test DB..."
	-docker compose rm -s -f pytest 2>/dev/null; docker compose -f docker-compose.yml stop postgres_test 2>/dev/null; true
	@echo ""
	@echo "✓ Tests complete!"
