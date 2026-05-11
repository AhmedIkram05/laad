.PHONY: help db-up db-down db-logs test-db-up test-db-down test-db-logs test pytest clean

help:
	@echo "LAAD Docker & Development Commands"
	@echo ""
	@echo "Database (Production):"
	@echo "  make db-up          Start PostgreSQL production database (port 5432)"
	@echo "  make db-down        Stop PostgreSQL production database"
	@echo "  make db-logs        View production database logs"
	@echo ""
	@echo "Database (Test):"
	@echo "  make test-db-up     Start isolated test database (port 5433)"
	@echo "  make test-db-down   Stop isolated test database"
	@echo "  make test-db-logs   View test database logs"
	@echo ""
	@echo "Testing:"
	@echo "  make pytest         Run full pytest suite against test database"
	@echo "  make test           Alias for pytest"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          Stop all containers and remove volumes"

# Production database
db-up:
	docker compose up -d
	@echo "✓ Production database started on localhost:5432"

db-down:
	docker compose down
	@echo "✓ Production database stopped"

db-logs:
	docker compose logs -f postgres

# Test database
test-db-up:
	docker compose -f docker-compose.test.yml up -d
	@echo "✓ Test database started on localhost:5433"

test-db-down:
	docker compose -f docker-compose.test.yml down
	@echo "✓ Test database stopped"

test-db-logs:
	docker compose -f docker-compose.test.yml logs -f postgres_test

# Testing
pytest: test-db-up
	@echo "Running pytest..."
	pytest -q

test: pytest

# Cleanup
clean:
	docker compose down -v
	docker compose -f docker-compose.test.yml down -v
	@echo "✓ All containers and volumes removed"
