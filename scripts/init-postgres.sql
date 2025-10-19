-- PostgreSQL Initialisierung für ASCII Sky
-- Wird automatisch beim ersten Start von PostgreSQL ausgeführt

-- Stelle sicher, dass wir in der richtigen Datenbank sind
\c asciisky;

-- Erstelle Erweiterungen
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ===== Asteroid Orbital Elements Tabelle =====
CREATE TABLE IF NOT EXISTS asteroid_elements (
    id SERIAL PRIMARY KEY,
    designation VARCHAR(50) NOT NULL UNIQUE,
    epoch DOUBLE PRECISION NOT NULL,
    a DOUBLE PRECISION NOT NULL,           -- Semi-major axis (AU)
    e DOUBLE PRECISION NOT NULL,           -- Eccentricity
    i DOUBLE PRECISION NOT NULL,           -- Inclination (degrees)
    om DOUBLE PRECISION NOT NULL,          -- Longitude of ascending node (degrees)
    w DOUBLE PRECISION NOT NULL,           -- Argument of perihelion (degrees)
    ma DOUBLE PRECISION NOT NULL,          -- Mean anomaly (degrees)
    n DOUBLE PRECISION,                    -- Mean motion (degrees/day)
    absolute_magnitude DOUBLE PRECISION,   -- H (absolute magnitude)
    slope_parameter DOUBLE PRECISION,      -- G (slope parameter)
    data_source VARCHAR(50),               -- 'MPC' or 'JPL'
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_asteroid_designation ON asteroid_elements(designation);
CREATE INDEX IF NOT EXISTS idx_asteroid_abs_mag ON asteroid_elements(absolute_magnitude);
CREATE INDEX IF NOT EXISTS idx_asteroid_updated ON asteroid_elements(last_updated);

-- ===== Comet Orbital Elements Tabelle =====
CREATE TABLE IF NOT EXISTS comet_elements (
    id SERIAL PRIMARY KEY,
    designation VARCHAR(100) NOT NULL UNIQUE,
    epoch DOUBLE PRECISION NOT NULL,
    q DOUBLE PRECISION NOT NULL,           -- Perihelion distance (AU)
    e DOUBLE PRECISION NOT NULL,           -- Eccentricity
    i DOUBLE PRECISION NOT NULL,           -- Inclination (degrees)
    om DOUBLE PRECISION NOT NULL,          -- Longitude of ascending node (degrees)
    w DOUBLE PRECISION NOT NULL,           -- Argument of perihelion (degrees)
    tp DOUBLE PRECISION NOT NULL,          -- Time of perihelion passage (JD)
    absolute_magnitude DOUBLE PRECISION,   -- M1 or H (absolute magnitude)
    slope_parameter DOUBLE PRECISION,      -- K1 or G (slope parameter)
    data_source VARCHAR(50),               -- 'MPC'
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_comet_designation ON comet_elements(designation);
CREATE INDEX IF NOT EXISTS idx_comet_abs_mag ON comet_elements(absolute_magnitude);
CREATE INDEX IF NOT EXISTS idx_comet_updated ON comet_elements(last_updated);

-- ===== Cached Positions Tabelle =====
CREATE TABLE IF NOT EXISTS cached_positions (
    id SERIAL PRIMARY KEY,
    object_id INTEGER NOT NULL,            -- Referenz zu asteroid_elements.id oder comet_elements.id
    object_type VARCHAR(20) NOT NULL,      -- 'asteroid' oder 'comet'
    location_key VARCHAR(100) NOT NULL,    -- 'lat+XX.XXXX_lon+YY.YYYY_el+ZZZZ'
    time_bucket VARCHAR(20) NOT NULL,      -- 'YYYYMMDDTHH' (6-hour buckets)
    positions BYTEA NOT NULL,              -- Serialisierte Position-Daten (pickle/msgpack)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    UNIQUE(object_id, object_type, location_key, time_bucket)
);

CREATE INDEX IF NOT EXISTS idx_cached_loc_time ON cached_positions(location_key, time_bucket);
CREATE INDEX IF NOT EXISTS idx_cached_expires ON cached_positions(expires_at);
CREATE INDEX IF NOT EXISTS idx_cached_type ON cached_positions(object_type);

-- ===== Data Update Tracking =====
CREATE TABLE IF NOT EXISTS data_updates (
    id SERIAL PRIMARY KEY,
    data_type VARCHAR(50) NOT NULL,        -- 'asteroids' oder 'comets'
    update_started TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_completed TIMESTAMP,
    records_updated INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'running',  -- 'running', 'completed', 'failed'
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_updates_type ON data_updates(data_type);
CREATE INDEX IF NOT EXISTS idx_updates_completed ON data_updates(update_completed);

-- ===== Statistics View =====
CREATE OR REPLACE VIEW cache_statistics AS
SELECT 
    object_type,
    COUNT(*) as total_entries,
    COUNT(DISTINCT location_key) as unique_locations,
    COUNT(DISTINCT time_bucket) as unique_time_buckets,
    MIN(created_at) as oldest_entry,
    MAX(created_at) as newest_entry,
    MIN(expires_at) as earliest_expiry,
    MAX(expires_at) as latest_expiry
FROM cached_positions
GROUP BY object_type;

-- ===== Cleanup Function =====
CREATE OR REPLACE FUNCTION cleanup_expired_positions()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM cached_positions
    WHERE expires_at < CURRENT_TIMESTAMP;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

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
    RAISE NOTICE 'Tables created: asteroid_elements, comet_elements, cached_positions, data_updates';
    RAISE NOTICE 'Ready for data import via nightly_data_updater.py';
END $$;
