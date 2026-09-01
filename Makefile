.PHONY: help all rebuild rebuild-backend rebuild-frontend clean logs train test test-backend test-frontend eval-ragas

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
	@echo "  make test         		Run ALL tests (backend + frontend + E2E) in Docker"
	@echo "  make test-backend 		Run backend tests only"
	@echo "  make test-frontend 		Run frontend tests only"
	@echo "  make test-e2e     		Run Playwright E2E tests (starts full stack)"
	@echo "  make test-e2e-quick		Run Playwright E2E tests (existing stack)"
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

test: test-backend test-frontend test-e2e

test-backend:
	@echo "==> Stopping any leftover test containers..."
	-docker compose stop postgres_test pytest 2>/dev/null; true
	-docker compose rm -f postgres_test pytest 2>/dev/null; true
	@echo "==> Starting backend test environment..."
	POSTGRES_HOST=postgres_test POSTGRES_DB=atm_platform_test docker compose up --no-deps -d backend
	docker compose up -d redis
	docker compose --profile test up -d postgres_test
	@echo "==> Waiting for test services to be ready..."
	@sleep 8
	-docker compose run --rm --build pytest
	@echo "==> Stopping backend test environment..."
	-docker compose stop postgres_test backend pytest redis 2>/dev/null; true
	-docker compose rm -f postgres_test backend pytest redis 2>/dev/null; true
	@echo ""
	@echo "✓ Backend tests complete!"

test-frontend:
	@echo "==> Running frontend tests..."
	docker compose run --rm frontend-test
	@echo ""
	@echo "✓ Frontend tests complete!"

test-e2e:
	@echo "==> Starting full stack for E2E tests..."
	docker compose up -d postgres kafka kafka-init chromadb redis ollama backend frontend
	@echo "==> Waiting for services to be healthy..."
	@sleep 15
	docker compose run --rm --build playwright
	@echo "==> Stopping E2E test stack..."
	-docker compose stop playwright 2>/dev/null; true
	-docker compose rm -f playwright 2>/dev/null; true
	@echo ""
	@echo "✓ E2E tests complete!"

test-e2e-quick:
	@echo "==> Running E2E tests against existing stack (assumes services are up)..."
	docker compose run --rm playwright
	@echo ""
	@echo "✓ E2E tests complete!"

# ── RAG Evaluation ────────────────────────────────────────────────────────────

eval-ragas:
	@echo "==> Running RAG evaluation (baseline/hybrid/agentic vs golden set)..."
	docker compose run --rm pytest sh -c "PYTHONPATH=/app python -m backend.tests.eval.run_ragas $(FLAGS)"
	@echo ""
	@echo "✓ RAG evaluation complete! See backend/tests/eval/results.json"

# ── IaC Compliance ─────────────────────────────────────────────────────────

checkov:
	@echo "==> Running checkov IaC compliance checks..."
	python3 scripts/checkov-compliance.py
	@echo ""
	@echo "✓ checkov compliance checks complete!"

# ── Upload Coverage ─────────────────────────────────────────────────────────

# Push full-suite coverage.xml (produced by `make test-backend`) to Codecov for
# the current HEAD. Merges with CI's fast uploads, so the badge reflects true
# coverage. Requires: export CODECOV_TOKEN=<repo upload token> and a pushed commit.
coverage-upload:
	@command -v codecov >/dev/null 2>&1 || (echo "==> Installing Codecov CLI..." && curl -sL --retry 3 --retry-all-errors https://cli.codecov.io/latest/macos/codecov -o /usr/local/bin/codecov && chmod +x /usr/local/bin/codecov)
	@test -f backend/coverage.xml || (echo "!! backend/coverage.xml missing — run make test-backend first" && exit 1)
	@test -n "$(CODECOV_TOKEN)" || (echo "!! CODECOV_TOKEN not set" && exit 1)
	@echo "==> Uploading coverage for $$(git rev-parse --short HEAD)..."
	@sed 's|/app/backend|backend|g' backend/coverage.xml > /tmp/coverage-clean.xml
	@codecov create-commit -t "$(CODECOV_TOKEN)" --git-service github -C $$(git rev-parse HEAD) -B $$(git rev-parse --abbrev-ref HEAD) && \
	codecov create-report -t "$(CODECOV_TOKEN)" -C $$(git rev-parse HEAD) && \
	codecov do-upload -t "$(CODECOV_TOKEN)" -C $$(git rev-parse HEAD) -F backend -f /tmp/coverage-clean.xml
	@rm -f /tmp/coverage-clean.xml
	@echo ""
	@echo "✓ Coverage uploaded! Badge updates in a few minutes."
