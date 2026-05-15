.PHONY: help all rebuild rebuild-backend clean logs retrain-offline pytest generate-training-data

help:
	@echo "LAAD Makefile — Essential commands"
	@echo ""
	@echo "  make all          		Start all services (postgres, kafka, chromadb, backend, generator, kafka-consumer, mlflow)"
	@echo "  make rebuild      		Full rebuild: remove ALL containers/volumes/images, then start fresh"
	@echo "  make rebuild-backend  	Rebuild backend image only, keep other services running"
	@echo "  make clean       		Stop all containers and remove volumes"
	@echo "  make logs         		Follow all service logs"
	@echo "  make retrain-offline  	 Retrain ML on offline dataset (all A1-A7 guaranteed)"
	@echo "  make training-data  	Generate offline training dataset (24h, all A1-A7)"
	@echo "  make pytest       		Run all tests in Docker (postgres_test + pytest containers)"
	@echo ""
	@echo "Services:"
	@echo "  Backend API:     		http://localhost:8000"
	@echo "  Kafka:            		http://localhost:9092"
	@echo "  ChromaDB:         		http://localhost:8001"
	@echo "  PostgreSQL:     		http://localhost:5434"
	@echo "  Test DB:         		http://localhost:5433"
	@echo "  MLflow UI:       		 http://localhost:5001"

# ── Start All ────────────────────────────────────────────────────────────────

all: ml-up
	docker compose up -d --build postgres kafka kafka-init chromadb backend generator kafka-consumer
	@echo ""
	@echo "✓ All services started!"
	@echo "  Backend API:     		http://localhost:8000"
	@echo "  Kafka:            		http://localhost:9092"
	@echo "  ChromaDB:         		http://localhost:8001"
	@echo "  PostgreSQL:     		http://localhost:5434"
	@echo "  Test DB:         		http://localhost:5433"
	@echo "  MLflow UI:       		 http://localhost:5001"
	@echo ""

# ── Full Rebuild ────────────────────────────────────────────────────────────

rebuild:
	@echo "==> Stopping all containers and removing all volumes/images..."
	-docker compose --profile ml down -v 2>/dev/null; true
	-docker compose --profile test down -v 2>/dev/null; true
	-docker compose down -v 2>/dev/null; true
	-docker compose down --remove-orphans 2>/dev/null; true
	@echo "==> Removing all LAAD volumes..."
	-docker volume rm laad_postgres_data laad_mlflow_artifacts laad_postgres_test_data laad_kafka_data laad_chroma_data 2>/dev/null; true
	@echo "==> Removing orphaned containers..."
	-docker compose down --remove-orphans 2>/dev/null; true
	@echo "==> Starting fresh (mlflow starts with --profile ml)..."
	docker compose up -d --build postgres kafka kafka-init chromadb backend generator kafka-consumer
	docker compose --profile ml up -d
	@echo ""
	@echo "✓ Rebuild complete!"
	@echo "  Backend API:     		http://localhost:8000"
	@echo "  Kafka:           		http://localhost:9092"
	@echo "  ChromaDB:         		http://localhost:8001"
	@echo "  PostgreSQL:     		http://localhost:5434"
	@echo "  Test DB:         		http://localhost:5433"
	@echo "  MLflow UI:       		 http://localhost:5001"

# ── Backend-only Rebuild ───────────────────────────────────────────────────

rebuild-backend:
	docker compose build backend generator kafka-consumer
	docker compose up -d --no-deps backend generator kafka-consumer
	@echo "✓ Backend and related images rebuilt and containers restarted"

# ── Stop All ─────────────────────────────────────────────────────────────

clean:
	@echo "==> Stopping all services and removing volumes..."
	-docker compose --profile ml down -v 2>/dev/null; true
	-docker compose --profile test down -v 2>/dev/null; true
	-docker compose down -v 2>/dev/null; true
	-docker compose down --remove-orphans 2>/dev/null; true
	@echo "✓ All services stopped and volumes removed"

# ── Follow Logs ─────────────────────────────────────────────────────────────

logs:
	docker compose logs -f

# ── Retrain ML Models ──────────────────────────────────────────────────────

retrain-offline:
	@echo "==> Retraining ML models on OFFLINE dataset..."
	docker compose exec -e USE_OFFLINE_DATA=true backend python -m backend.src.anomaly_detection.ml.train
	@echo ""
	@echo "✓ Retrain complete!"
	@echo "  View training run at: http://localhost:5001"

# ── Run Tests ──────────────────────────────────────────────────────────────

pytest:
	@echo "==> Stopping any leftover test containers..."
	-docker compose stop postgres_test pytest 2>/dev/null; true
	-docker compose rm -f postgres_test pytest 2>/dev/null; true
	@echo "==> Starting test environment and running tests..."
	docker compose --profile test up -d postgres_test
	@echo "==> Waiting for test DB to be ready..."
	@sleep 5
	docker compose run --rm --no-deps pytest
	@echo "==> Stopping test environment..."
	-docker compose stop postgres_test pytest 2>/dev/null; true
	-docker compose rm -f postgres_test pytest 2>/dev/null; true
	@echo ""
	@echo "✓ Tests complete!"

# ── MLflow profile shortcut ─────────────────────────────────────────────────

ml-up:
	@docker compose --profile ml up -d
	@echo "✓ MLflow started on http://localhost:5001"
