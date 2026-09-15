# S0-BOOT-001 command surface. Real implementations arrive with their owning tasks.
UV := uv --project backend

.PHONY: sync test lint typecheck versions contracts migration-status seed stage-scenario api

sync: ## Install backend dependencies (S0-BOOT-001)
	$(UV) sync --group dev

test: ## Run backend tests (S0-BOOT-001)
	$(UV) run --group dev pytest

lint: ## Ruff lint and format check (S0-CONFIG-001)
	$(UV) run --group dev ruff check backend
	$(UV) run --group dev ruff format --check backend

typecheck: ## Strict basedpyright (S0-CONFIG-001)
	$(UV) run --group dev basedpyright -p backend/pyrightconfig.json

versions: ## Dependency and version report (S0-CONFIG-001)
	$(UV) run --group dev python -c "from worldsim.infrastructure.settings import dependency_report; print(dependency_report())"

contracts: ## Generate domain JSON Schema and OpenAPI (S0-DOM-001; OpenAPI arrives with S0-API-001)
	$(UV) run --group dev python -m worldsim.domain.schema --out content/schemas/domain-schema.json
	$(UV) run --group dev python -m worldsim.domain.schema --out content/schemas/domain-schema.json --check
	$(UV) run --group dev python -m worldsim.interfaces.http.export --out content/schemas/openapi.json

migration-status: ## Alembic heads and current revision (S0-DB-001)
	$(UV) run --group dev alembic -c backend/alembic.ini check
	$(UV) run --group dev alembic -c backend/alembic.ini current

seed: ## Import the Stage 0 seed (S0-API-001 serves the same path over HTTP)
	$(UV) run --group dev python -m worldsim.interfaces.cli seed

stage-scenario: ## Run the Stage 0 foundation scenario and evidence bundle (S0-GATE-001)
	$(UV) run --group dev pytest backend/tests/test_stage0_foundation.py

api: ## Serve the Stage 0 HTTP boundary on loopback (S0-API-001)
	$(UV) run --group dev python -m worldsim.interfaces.cli serve
