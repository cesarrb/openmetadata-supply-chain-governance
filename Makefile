# One-command rebuild of the whole demo.  `make all` after `make up`.
SHELL := /bin/bash
COMPOSE := docker compose -f docker/docker-compose-postgres.yml
BI := docker compose -f docker/docker-compose-bi.yml
DBT := cd dbt && DBT_PROFILES_DIR=. uv run dbt
INGEST := scripts/run_ingestion.sh

.PHONY: up down init-db data dbt token bi ingest governance quality contracts scorecard validate access all

up:            ## start OpenMetadata (Postgres, Elasticsearch, server, ingestion) + Metabase - needs ~6 GB RAM
	$(COMPOSE) up -d
	@until curl -sf localhost:8585/api/v1/system/version >/dev/null; do sleep 5; done; echo "OpenMetadata up on http://localhost:8585"
	$(BI) up -d
	@until curl -sf localhost:3000/api/health | grep -q ok; do sleep 5; done; echo "Metabase up on http://localhost:3000"

down:          ## stop all containers (data is kept in docker/docker-volume)
	-$(BI) stop
	$(COMPOSE) stop

init-db:       ## create the demo ERP database and its roles (once)
	docker exec -i openmetadata_postgresql psql -U postgres < data/init_erp.sql || true

data:          ## (re)generate the synthetic SAP-style ERP tables
	uv run python data/generate_sap_data.py

dbt:           ## build staging + marts, docs catalog, then tests (tests last so run_results.json keeps them)
	$(DBT) run
	$(DBT) docs generate
	-$(DBT) test

token:
	scripts/get_token.sh

bi:            ## Metabase: admin, ERP connection, 3 SQL questions, Supply Chain Performance dashboard
	uv run python scripts/setup_metabase.py

ingest:        ## metadata -> dbt (lineage + test results) -> profiler -> PII auto-classification
	$(INGEST) ingestion/01_postgres_metadata.yaml ingest
	$(INGEST) ingestion/02_dbt.yaml ingest
	$(INGEST) ingestion/03_profiler.yaml profile
	$(INGEST) ingestion/04_auto_classification.yaml classify
	$(INGEST) ingestion/05_metabase.yaml ingest

governance:    ## owners, domains, glossary, classification, certification, dashboard lineage
	uv run python scripts/apply_governance.py

quality:       ## OpenMetadata-native data-quality tests
	uv run python scripts/data_quality.py

contracts:     ## data contracts for certified tables: create, validate, export ODCS YAML to contracts/
	uv run python scripts/apply_contracts.py

scorecard:     ## governance KPIs measured from the live catalogue -> docs/SCORECARD.md
	uv run python scripts/scorecard.py

validate:      ## static checks on governance YAML (also runs in CI)
	uv run python scripts/validate_governance.py

access:        ## prove the access policy per persona
	uv run python scripts/check_access.py

all: validate data dbt token bi ingest governance quality contracts scorecard access
