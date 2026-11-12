# One-command rebuild of the whole demo.  `make all` after `make up`.
SHELL := /bin/bash
COMPOSE := docker compose -f docker/docker-compose-postgres.yml
DBT := cd dbt && DBT_PROFILES_DIR=. uv run dbt
INGEST := scripts/run_ingestion.sh

.PHONY: up down init-db data dbt token ingest governance quality all

up:            ## start OpenMetadata (Postgres, Elasticsearch, server, ingestion) - needs ~5 GB RAM
	$(COMPOSE) up -d
	@until curl -sf localhost:8585/api/v1/system/version >/dev/null; do sleep 5; done; echo "OpenMetadata up on http://localhost:8585"

down:          ## stop all containers (data is kept in docker/docker-volume)
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

ingest:        ## metadata -> dbt (lineage + test results) -> profiler -> PII auto-classification
	$(INGEST) ingestion/01_postgres_metadata.yaml ingest
	$(INGEST) ingestion/02_dbt.yaml ingest
	$(INGEST) ingestion/03_profiler.yaml profile
	$(INGEST) ingestion/04_auto_classification.yaml classify

governance:    ## owners, domains, glossary, classification, certification, dashboard lineage
	uv run python scripts/apply_governance.py

quality:       ## OpenMetadata-native data-quality tests
	uv run python scripts/data_quality.py

all: data dbt token ingest governance quality
