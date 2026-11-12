-- Separate database for the demo ERP + analytics warehouse (lives in the same Postgres
-- container as OpenMetadata's own metadata store, to save RAM on a laptop).
CREATE ROLE erp_admin  LOGIN PASSWORD 'erp_admin';   -- owns raw data and runs dbt
CREATE ROLE erp_reader LOGIN PASSWORD 'erp_reader';  -- read-only, used by OpenMetadata ingestion
CREATE DATABASE erp OWNER erp_admin;
