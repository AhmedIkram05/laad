.PHONY: help all rebuild clean logs

help:
	@echo "LAAD Makefile — Essential commands"
	@echo ""
	@echo "  make all         Start all services (postgres, backend, generator, test-db, mlflow)"
	@echo "  make rebuild     Clean rebuild (stop, remove volumes, rebuild images, start all)"
	@echo "  make clean       Stop all containers and remove volumes"
	@echo "  make logs        Follow all service logs"
	@echo ""
	@echo "Services run on:"
	@echo "  Backend API:     http://localhost:8000"
	@echo "  PostgreSQL:      localhost:5432"
	@echo "  Test DB:         localhost:5433"
	@echo "  MLflow UI:       http://localhost:5000"
	@echo ""

# ── Primary Commands ──────────────────────────────────────────────────────────

all:
	docker compose up -d --build postgres backend generator
	docker compose -f docker-compose.test.yml up -d
	docker compose --profile ml up -d
	@echo ""
	@echo "✓ All services started!"
	@echo "  Backend API:     http://localhost:8000"
	@echo "  PostgreSQL:      localhost:5432"
	@echo "  Test DB:         localhost:5433"
	@echo "  MLflow UI:       http://localhost:5000"
	@echo ""

rebuild: clean all
	@echo "✓ Rebuild complete!"

clean:
	docker compose down -v
	docker compose --profile generator down -v
	docker compose --profile ml down -v
	docker compose -f docker-compose.test.yml down -v
	@echo "✓ All services stopped and volumes removed"

logs:
	docker compose logs -f
	docker compose --profile ml down -v
	docker compose -f docker-compose.test.yml down -v
	@echo "All containers and volumes removed"