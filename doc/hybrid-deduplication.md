# Distributed Duplicate-Work Protection

## Scope

ASCII Sky combines deterministic RabbitMQ message IDs with PostgreSQL advisory locks. The two mechanisms have different roles:

- `message_id` identifies equivalent tasks for logging and diagnostics. RabbitMQ classic queues do **not** reject a second message merely because the ID is equal.
- PostgreSQL advisory locks serialize computations with the same computation key across processes and hosts connected to the same database.
- RabbitMQ acknowledgements and persistent messages provide at-least-once delivery semantics. This is not exactly-once processing.

The protection therefore targets concurrent duplicate computation, not duplicate queue entries.

## Processing Flow

```text
publisher
  -> deterministic message_id + persistent RabbitMQ message
  -> classic queue
  -> worker derives computation key
  -> pg_advisory_lock(hash(computation key))
  -> compute and upsert cached result
  -> pg_advisory_unlock(...)
  -> acknowledge RabbitMQ message
```

Precompute keys contain the object kind, normalized location key, and UTC time bucket. The implementation is in:

- `precompute_coordinator.py`: publishes precompute tasks with deterministic IDs.
- `workers/unified_worker.py`: generates IDs and processes precompute, on-demand, and RPC tasks.
- `workers/precompute_worker.py`: dedicated precompute consumer used by the production main-server stack.
- `db_utils.py`: `_advisory_lock_id()` and `computation_lock()`.
- `workers/worker_utils.py`: declares the standard exchanges and queues.

## Lock Semantics and Limitations

`computation_lock()` uses a blocking, session-level `pg_advisory_lock()`. A competing worker waits until the holder releases the lock. Locks are explicitly released in `finally` and PostgreSQL also releases them when the database connection closes.

Important constraints:

- PostgreSQL advisory locks do not have a TTL. The current `ttl_seconds` argument is included in a `pg_notify()` payload, but no listener in this repository expires the lock.
- The 32-bit integer lock ID is derived from the first four bytes of an MD5 digest. Hash collisions are unlikely but possible and would cause unrelated work to serialize.
- All participating workers must use the same PostgreSQL database and the same key construction.
- The lock covers the computation and database write. It does not prevent duplicate messages from occupying queue capacity.
- A waiting task currently computes after obtaining the lock; the worker does not recheck the position cache inside the lock. Duplicate messages can therefore still cause sequential duplicate computation.

These properties mean that descriptions such as “100% deduplication” or “exactly once” are not accurate for the current implementation.

## RabbitMQ Queues and Expiration

The application uses standard RabbitMQ 4.1 classic queues; no broker-side deduplication plugin is configured.

| Queue | Purpose | Queue-level TTL |
|---|---|---:|
| `precompute.tasks` | Scheduled asteroid/comet/sunpath work | none |
| `asteroid.compute` | On-demand asteroid work | 1 hour |
| `comet.compute` | On-demand comet work | 1 hour |
| `computation.status` | Worker status | none |

`UnifiedWorker.send_task_with_deduplication()` additionally publishes with a fixed five-minute per-message expiration. Despite their names, `ASCII_SKY_DEDUPLICATION_TTL`, `ASCII_SKY_ADVISORY_LOCK_TTL`, and `ENABLE_HYBRID_DEDUPLICATION` are not currently read by the Python implementation. They remain in Compose/examples for compatibility and should not be treated as effective runtime controls.

## Configuration

The settings that currently affect worker delivery are:

```bash
RABBITMQ_URL=amqp://admin:changeme@rabbitmq:5672/
RABBITMQ_PREFETCH_COUNT=1
RABBITMQ_HEARTBEAT=60
```

Worker counts are selected by Compose scaling:

```bash
PRECOMPUTE_WORKERS=4  # production main-server precompute workers
UNIFIED_WORKERS=8     # unified workers on worker hosts
```

## Verification and Monitoring

The lightweight test verifies stable message-ID generation and basic lock behavior:

```bash
python test_hybrid_deduplication.py
```

It is not a proof of exactly-once behavior or a multi-host load benchmark.

RabbitMQ queue depth and consumers are visible at `http://localhost:15672`. Active and waiting PostgreSQL advisory locks can be inspected with:

```sql
SELECT pid, mode, granted
FROM pg_locks
WHERE locktype = 'advisory'
ORDER BY granted, pid;
```

No fixed memory or throughput improvement is claimed: the repository contains no reproducible before/after benchmark for the previously documented `-80%` memory or `+35%` throughput figures.

## Operational Commands

```bash
./scripts/hybrid-setup.sh local
./scripts/hybrid-setup.sh local --clean  # destructive: removes local volumes
./scripts/hybrid-setup.sh test           # expects an existing production-style environment
./scripts/hybrid-setup.sh summary
```

For multi-host deployment, see [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md). The supported introductory path remains the local stack documented in the repository [README](../README.md).

Last reviewed against the code: 2026-06-30.
