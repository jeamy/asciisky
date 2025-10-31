-- Computation Locks Table
-- Prevents redundant calculations for the same bucket

CREATE TABLE IF NOT EXISTS computation_locks (
    lock_key VARCHAR(200) PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- Index for fast expiry checks
CREATE INDEX IF NOT EXISTS idx_computation_locks_expiry 
ON computation_locks(expires_at);

-- Cleanup function (can be called periodically)
CREATE OR REPLACE FUNCTION cleanup_expired_computation_locks()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM computation_locks WHERE expires_at < NOW();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON TABLE computation_locks IS 'Prevents redundant bucket calculations';
COMMENT ON COLUMN computation_locks.lock_key IS 'Format: computing:{type}:{location_key}:{time_bucket}';
COMMENT ON COLUMN computation_locks.expires_at IS 'Lock expires after 5 minutes (default TTL)';
