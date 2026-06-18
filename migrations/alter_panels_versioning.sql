-- One-time, idempotent migration: upgrade an EXISTING panels DB (pre-parity
-- schema) to the versioning-parity schema WITHOUT data loss. Additive only —
-- adds columns, constraints and one table; never drops or rewrites data.
-- Wrapped in a transaction, so a constraint violation rolls the whole thing
-- back. Safe to re-run (each step is guarded).
--
-- Apply:
--   docker exec -i refgen-core-postgres-1 psql -U postgres -d panels \
--       < migrations/alter_panels_versioning.sql
--
-- After applying, rebuild + restart panels-svc so the code matches the schema.

BEGIN;

-- 1. Version-consumption trace — the unlock escape-hatch guard reads this.
--    NULL on every existing row (nothing has been consumed by a run yet).
ALTER TABLE panel_versions ADD COLUMN IF NOT EXISTS consumed_at timestamptz;
ALTER TABLE panel_versions ADD COLUMN IF NOT EXISTS consumed_by varchar(128);

-- 2. Integrity constraints (names match what create_all produces on a fresh DB).
--    If existing data violated either, ADD CONSTRAINT errors and the whole
--    transaction rolls back — no half-applied migration.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'panel_versions_content_hash_key') THEN
        ALTER TABLE panel_versions
            ADD CONSTRAINT panel_versions_content_hash_key UNIQUE (content_hash);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'uq_panel_version') THEN
        ALTER TABLE panel_versions
            ADD CONSTRAINT uq_panel_version UNIQUE (panel_id, version);
    END IF;
END $$;

-- 3. Curated-region table — part of the locked snapshot. "end" is quoted
--    because it is a reserved word (matches the SQLAlchemy-generated DDL).
CREATE TABLE IF NOT EXISTS panel_custom_regions (
    id        serial PRIMARY KEY,
    panel_id  integer NOT NULL REFERENCES panels(id) ON DELETE CASCADE,
    chr       varchar(10) NOT NULL,
    start     bigint NOT NULL,
    "end"     bigint NOT NULL,
    name      varchar(120) NOT NULL,
    kind      varchar(20) DEFAULT 'other',
    hgvs      varchar(200),
    note      text,
    added_by  varchar(64),
    added_at  timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_panel_custom_regions_panel_id
    ON panel_custom_regions (panel_id);

COMMIT;
