-- PostgreSQL Initialisierung für ASCII Sky
-- Wird automatisch beim ersten Start von PostgreSQL ausgeführt

-- Stelle sicher, dass wir in der richtigen Datenbank sind
\c asciisky;

-- Erstelle Erweiterungen
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ===== Asteroid Elements Tabelle =====
CREATE TABLE IF NOT EXISTS asteroid_elements (
    id SERIAL PRIMARY KEY,
    designation VARCHAR(50) NOT NULL UNIQUE,
    h_mag DOUBLE PRECISION,                -- H (absolute magnitude)
    orbit_data BYTEA,                      -- Serialized orbit data (pickle)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_asteroid_designation ON asteroid_elements(designation);
CREATE INDEX IF NOT EXISTS idx_asteroid_h_mag ON asteroid_elements(h_mag);

-- ===== Asteroid DataFrames Tabelle =====
CREATE TABLE IF NOT EXISTS asteroid_dataframes (
    id INTEGER PRIMARY KEY DEFAULT 1,
    computed_at TIMESTAMP NOT NULL,
    dataframe_pickle BYTEA NOT NULL,
    CONSTRAINT single_row CHECK (id = 1)
);

CREATE INDEX IF NOT EXISTS idx_asteroid_df_computed ON asteroid_dataframes(computed_at);

-- ===== Comet Elements Tabelle =====
CREATE TABLE IF NOT EXISTS comet_elements (
    id SERIAL PRIMARY KEY,
    designation VARCHAR(100) NOT NULL UNIQUE,
    m1_mag DOUBLE PRECISION,               -- M1 (absolute magnitude)
    orbit_data BYTEA,                      -- Serialized orbit data (pickle)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_comet_designation ON comet_elements(designation);
CREATE INDEX IF NOT EXISTS idx_comet_m1_mag ON comet_elements(m1_mag);

-- ===== Comet DataFrames Tabelle =====
CREATE TABLE IF NOT EXISTS comet_dataframes (
    id INTEGER PRIMARY KEY DEFAULT 1,
    computed_at TIMESTAMP NOT NULL,
    dataframe_pickle BYTEA NOT NULL,
    CONSTRAINT single_row CHECK (id = 1)
);

CREATE INDEX IF NOT EXISTS idx_comet_df_computed ON comet_dataframes(computed_at);

-- ===== Cached Positions Tabelle =====
CREATE TABLE IF NOT EXISTS cached_positions (
    id SERIAL PRIMARY KEY,
    object_type VARCHAR(20) NOT NULL,      -- 'asteroid' oder 'comet'
    object_id INTEGER NOT NULL,            -- Referenz zu asteroid_elements.id oder comet_elements.id
    location_key VARCHAR(100) NOT NULL,    -- 'lat+XX.XXXX_lon+YY.YYYY_el+ZZZZ'
    time_bucket VARCHAR(20) NOT NULL,      -- 'YYYYMMDDTHH' (1-hour buckets)
    observer_lat DOUBLE PRECISION NOT NULL,
    observer_lon DOUBLE PRECISION NOT NULL,
    observer_elevation DOUBLE PRECISION NOT NULL,
    computed_at TIMESTAMP NOT NULL,
    position_data BYTEA NOT NULL,          -- Serialisierte Position-Daten (pickle)
    UNIQUE(object_type, location_key, time_bucket)
);

CREATE INDEX IF NOT EXISTS idx_cached_loc_time ON cached_positions(location_key, time_bucket);
CREATE INDEX IF NOT EXISTS idx_cached_computed ON cached_positions(computed_at);
CREATE INDEX IF NOT EXISTS idx_cached_type ON cached_positions(object_type);

-- ===== Data Update Tracking =====
CREATE TABLE IF NOT EXISTS data_updates (
    id SERIAL PRIMARY KEY,
    update_type VARCHAR(50) NOT NULL,      -- 'asteroids' oder 'comets'
    status VARCHAR(20) NOT NULL,           -- 'success', 'failed'
    message TEXT,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_updates_type ON data_updates(update_type);
CREATE INDEX IF NOT EXISTS idx_updates_updated ON data_updates(updated_at);

-- ===== User and Settings Tables =====
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    settings JSONB NOT NULL,
    last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_settings_updated ON user_settings(last_updated);

-- Cleanup old entries periodically
CREATE OR REPLACE FUNCTION cleanup_old_positions(retention_days INTEGER DEFAULT 60)
RETURNS void AS $$
BEGIN
    DELETE FROM cached_positions 
    WHERE computed_at < NOW() - (GREATEST(retention_days, 0) * INTERVAL '1 day');
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- Computation Locks
-- Using PostgreSQL Advisory Locks instead of custom table
-- =====================================================
-- No table needed - using pg_advisory_lock() functions
-- Benefits: automatic cleanup, better performance, distributed

-- ===== Statistics View =====
CREATE OR REPLACE VIEW cache_statistics AS
SELECT 
    object_type,
    COUNT(*) as total_entries,
    COUNT(DISTINCT location_key) as unique_locations,
    COUNT(DISTINCT time_bucket) as unique_time_buckets,
    MIN(computed_at) as oldest_entry,
    MAX(computed_at) as newest_entry
FROM cached_positions
GROUP BY object_type;

-- ===== Grants =====
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO asciisky;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO asciisky;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO asciisky;

-- ===== Initial Data =====
-- Keine initialen Daten - werden vom nightly_data_updater.py geladen

-- ===== Completion Message =====
DO $$
BEGIN
    RAISE NOTICE 'ASCII Sky PostgreSQL database initialized successfully!';
    RAISE NOTICE 'Tables created: asteroid_elements, asteroid_dataframes, comet_elements, comet_dataframes, cached_positions, data_updates';
    RAISE NOTICE 'Using PostgreSQL Advisory Locks for computation coordination';
    RAISE NOTICE 'Ready for data import via nightly_data_updater.py';
END $$;
