.PHONY: help all rebuild rebuild-backend rebuild-frontend clean logs train test test-backend test-frontend

help:
	@echo "LAAD Makefile — Essential commands"
	@echo ""
	@echo "  make all          		Start all services (postgres, kafka, chromadb, redis, ollama, backend, generator, kafka-consumer, mlflow, frontend)"
	@echo "  make rebuild      		Full rebuild: remove ALL containers/volumes/images, then start fresh"
	@echo "  make rebuild-backend  	Rebuild backend image only, keep other services running"
	@echo "  make rebuild-frontend 	Rebuild frontend image only, keep other services running"
	@echo "  make clean       		Stop all containers and remove ALL volumes"
	@echo "  make logs         		Follow all service logs"
	@echo "  make train        		Generate training data + retrain ML models (XGBoost & IF)"
	@echo "  make test         		Run ALL tests (backend + frontend) in Docker"
	@echo "  make test-backend 		Run backend tests only"
	@echo "  make test-frontend 		Run frontend tests only"
	@echo ""
	@echo "Services:"
	@echo "  Frontend UI:       		http://localhost:5173"
	@echo "  Backend API:     		http://localhost:8000"
	@echo "  Kafka:            		http://localhost:9092"
	@echo "  ChromaDB:         		http://localhost:8001"
	@echo "  Redis:           		http://localhost:6379"
	@echo "  PostgreSQL:     		http://localhost:5434"
	@echo "  Test DB:         		http://localhost:5433"
	@echo "  MLflow UI:       		 http://localhost:5001"
	@echo ""

# ── Start All ────────────────────────────────────────────────────────────────

all:
	docker compose --profile ml up -d
	docker compose up -d --build postgres kafka kafka-init chromadb redis ollama ollama-init backend generator kafka-consumer frontend
	@echo ""
	@echo "✓ All services started!"
	@echo "  Frontend UI:       		http://localhost:5173"
	@echo "  Backend API:     		http://localhost:8000"
	@echo "  Kafka:            		http://localhost:9092"
	@echo "  ChromaDB:         		http://localhost:8001"
	@echo "  Ollama:           		http://localhost:11435"
	@echo "  Redis:           		http://localhost:6379"
	@echo "  PostgreSQL:     		http://localhost:5434"
	@echo "  Test DB:         		http://localhost:5433"
	@echo "  MLflow UI:        		http://localhost:5001"
	@echo ""

# ── Full Rebuild ────────────────────────────────────────────────────────────

rebuild:
	@echo "==> Stopping all containers and removing all volumes/images..."
	-docker compose --profile ml down -v --remove-orphans 2>/dev/null; true
	-docker compose --profile test down -v --remove-orphans 2>/dev/null; true
	-docker compose down -v --remove-orphans 2>/dev/null; true
	@echo "==> Removing all LAAD volumes..."
	-docker volume rm laad_postgres_data laad_postgres_test_data laad_kafka_data laad_chroma_data laad_ollama_data laad_redis_data laad_mlflow_artifacts 2>/dev/null; true
	@echo "==> Starting fresh..."
	docker compose up -d --build postgres kafka kafka-init chromadb redis ollama ollama-init backend generator kafka-consumer frontend
	docker compose --profile ml up -d
	@echo ""
	@echo "✓ Rebuild complete!"
	@echo "  Frontend UI:       	http://localhost:5173"
	@echo "  Backend API:     		http://localhost:8000"
	@echo "  Kafka:           		http://localhost:9092"
	@echo "  ChromaDB:        		http://localhost:8001"
	@echo "  Ollama:          		http://localhost:11435"
	@echo "  Redis:           		http://localhost:6379"
	@echo "  PostgreSQL:     		http://localhost:5434"
	@echo "  Test DB:         		http://localhost:5433"
	@echo "  MLflow UI:       		http://localhost:5001"

# ── Backend-only Rebuild ───────────────────────────────────────────────────

rebuild-backend:
	docker compose build backend
	docker compose up -d --no-deps backend generator kafka-consumer
	@echo "✓ Backend image rebuilt and containers restarted (backend, generator, kafka-consumer all share ./backend/Dockerfile)"

# ── Frontend-only Rebuild ──────────────────────────────────────────────────

rebuild-frontend:
	docker compose build frontend
	docker compose up -d --no-deps frontend
	@echo "✓ Frontend image rebuilt and container restarted"

# ── Delete All ─────────────────────────────────────────────────────────────

clean:
	@echo "==> Stopping all services and removing ALL volumes..."
	-docker compose --profile ml down -v --remove-orphans 2>/dev/null; true
	-docker compose --profile test down -v --remove-orphans 2>/dev/null; true
	-docker compose down -v --remove-orphans 2>/dev/null; true
	-docker volume rm laad_mlflow_artifacts 2>/dev/null; true
	@echo "✓ All services stopped and all volumes removed"

# ── Follow Logs ─────────────────────────────────────────────────────────────

logs:
	docker compose logs -f

# ── Train ML Models ────────────────────────────────────────────────────────

train:
	@echo "==> Generating offline training dataset..."
	docker compose exec -T backend python -u -m backend.generator.training_dataset
	@echo "==> Training ML models (XGBoost + Isolation Forest)..."
	docker compose exec -T -e USE_OFFLINE_DATA=true -e TRAINING_DATA_PATH=/app/backend/src/anomaly_detection/ml/artifacts/training_data.json backend python -u -m backend.src.anomaly_detection.ml.train
	@echo ""
	@echo "✓ Training complete!"
	@echo "  View training run at: http://localhost:5001"

# ── Run Tests ──────────────────────────────────────────────────────────────

test: test-backend test-frontend

test-backend:
	@echo "==> Stopping any leftover test containers..."
	-docker compose stop postgres_test pytest 2>/dev/null; true
	-docker compose rm -f postgres_test pytest 2>/dev/null; true
	@echo "==> Starting backend test environment..."
	docker compose --profile test up -d postgres_test
	@echo "==> Waiting for test DB to be ready..."
	@sleep 5
	docker compose run --rm --build pytest
	@echo "==> Stopping backend test environment..."
	-docker compose stop postgres_test pytest 2>/dev/null; true
	-docker compose rm -f postgres_test pytest 2>/dev/null; true
	@echo ""
	@echo "✓ Backend tests complete!"

test-frontend:
	@echo "==> Running frontend tests..."
	docker compose run --rm frontend-test
	@echo ""
	@echo "✓ Frontend tests complete!"
