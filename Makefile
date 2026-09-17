# S0-BOOT-001 command surface. Real implementations arrive with their owning tasks.
UV := uv --project backend

.PHONY: sync test lint typecheck versions contracts migration-status seed stage-scenario api backup restore-check

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
	$(UV) run --group dev python backend/scripts/gen_ts_client.py --out content/clients/worldsim.ts

migration-status: ## Alembic heads and current revision (S0-DB-001)
	$(UV) run --group dev alembic -c backend/alembic.ini check
stage-scenario: ## Run the Stage 0 foundation scenario and evidence bundle (S0-GATE-001)
	$(UV) run --group dev pytest backend/tests/test_stage0_foundation.py

stage1-scenario: ## Run the Stage 1 three-phase scenario and evidence bundle (S1-GATE-001)
	$(UV) run --group dev pytest backend/tests/test_stage1_gate.py

api: ## Serve the Stage 0 HTTP boundary on loopback (S0-API-001)
	$(UV) run --group dev python -m worldsim.interfaces.cli serve

backup: ## pg_dump the compose database to backups/ (S5-HARD-001)
	mkdir -p backups
	docker compose exec -T db pg_dump -U $${POSTGRES_USER:-worldsim} $${POSTGRES_DB:-worldsim} > backups/worldsim-$$(date +%Y%m%d-%H%M%S).sql

restore-check: ## Restore BACKUP=dump.sql into a scratch DB and compare counts (S5-HARD-001)
	test -n "$(BACKUP)" || (echo "usage: make restore-check BACKUP=backups/<file>.sql" && exit 1)
	docker compose exec -T db psql -U $${POSTGRES_USER:-worldsim} -d postgres -c "DROP DATABASE IF EXISTS worldsim_verify;"
	docker compose exec -T db psql -U $${POSTGRES_USER:-worldsim} -d postgres -c "CREATE DATABASE worldsim_verify;"
	docker compose exec -T db psql -U $${POSTGRES_USER:-worldsim} -d worldsim_verify -q -f - < $(BACKUP)
	docker compose exec -T db psql -U $${POSTGRES_USER:-worldsim} -d worldsim_verify -t -c "SELECT (SELECT count(*) FROM world_event), (SELECT count(*) FROM world), (SELECT version_num FROM alembic_version);"
	docker compose exec -T db psql -U $${POSTGRES_USER:-worldsim} -d postgres -c "DROP DATABASE worldsim_verify;"
