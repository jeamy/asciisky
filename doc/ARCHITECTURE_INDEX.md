# ASCII Sky Architecture Documentation

This index describes the code as reviewed on 2026-06-30. The supported introductory deployment is the single-workstation Docker Compose stack in the repository [README](../README.md); multi-host material is experimental.

## Documentation Map

| Document | Scope |
|---|---|
| [ARCHITECTURE_FLOW_API.md](ARCHITECTURE_FLOW_API.md) | HTTP request, cache, RabbitMQ, worker, and sunpath flows |
| [ARCHITECTURE_CACHE.md](ARCHITECTURE_CACHE.md) | PostgreSQL position cache, filesystem DataFrames, filtering, and invalidation |
| [ARCHITECTURE_DATABASE.md](ARCHITECTURE_DATABASE.md) | PostgreSQL schema and persistence helpers |
| [hybrid-deduplication.md](hybrid-deduplication.md) | Actual message-ID and advisory-lock semantics and limitations |
| [ARCHITECTURE_USERS.md](ARCHITECTURE_USERS.md) | User-system design history and current implementation status |
| [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) | Experimental multi-host deployment |
| [FIREWALL_SETUP.md](FIREWALL_SETUP.md) | Firewall guidance for that multi-host deployment |
| [asteroids.md](asteroids.md) | Asteroid orbit, H–G magnitude, events, and endpoint |
| [comets.md](comets.md) | Comet orbit, M1/k1 magnitude, events, and endpoint |
| [planets.md](planets.md) | Sun, Moon, and planet computation |
| [CODE_QUALITY_REPORT.md](CODE_QUALITY_REPORT.md) | Dated audit record; not a current architecture contract |

## Runtime Overview

```text
browser -> FastAPI
             |-> /api/celestial: direct Skyfield calculation
             |-> /api/celestial/sunpath: PostgreSQL cache + background task
             `-> asteroid/comet endpoints
                    |-> PostgreSQL cached_positions hit -> filter -> response
                    `-> miss -> RabbitMQ -> worker -> compute -> PostgreSQL

nightly_data_updater -> MPC download/parse -> DataFrame files + PostgreSQL metadata
precompute_coordinator -> precompute.tasks -> dedicated or unified workers
```

Asteroid and comet positions use normalized location keys and one-hour UTC buckets. User magnitude limits are applied to cached results in the API. Sun, Moon, and planets are computed synchronously. The yearly sunpath has its own `cached_positions` entries with `object_type='sunpath'`.

## Main Components

```text
main.py                         FastAPI application and router registration
api/routes/                     HTTP endpoints
api/cache_interpolation.py      nearest-bucket cache access
api/smart_interpolation.py      optional smart/on-demand cache path
api/computation.py              celestial and sunpath calculations
bright_asteroids.py             vectorized asteroid pipeline
comets.py                       vectorized comet pipeline
cache_utils.py                  location normalization and time buckets
db_utils.py                     PostgreSQL persistence and advisory locks
precompute_coordinator.py       future-bucket task publisher
workers/precompute_worker.py    compatibility entry point for unified worker
workers/unified_worker.py       precompute/on-demand/RPC consumer
workers/worker_utils.py         queue declarations and shared resources
```

There are no `workers/asteroid_worker.py` or `workers/comet_worker.py` modules. On-demand queues are consumed by the unified worker.

## Persistence

PostgreSQL contains `asteroid_elements`, `asteroid_dataframes`, `comet_elements`, `comet_dataframes`, `cached_positions`, `data_updates`, `users`, and `user_settings`. The active loaders also use pickled DataFrame files under `DATA_DIR`. See [ARCHITECTURE_DATABASE.md](ARCHITECTURE_DATABASE.md) for the schema and the distinction between these stores.

Cached positions are upserted by `(object_type, location_key, time_bucket)`. Although a bucket represents a fixed instant, results can become stale when orbital elements or algorithms change; “immutable” does not mean they never need invalidation.

## Queues and Concurrency

- `precompute.tasks`: durable priority queue for scheduled asteroid, comet, and sunpath tasks.
- `asteroid.compute` and `comet.compute`: durable classic priority queues with a one-hour queue-level message TTL.
- `computation.status`: durable status queue.
- `computation.direct`: direct exchange for on-demand tasks.

Deterministic `message_id` values do not provide broker-side deduplication. Worker-side PostgreSQL advisory locks serialize matching precompute keys, with the limitations documented in [hybrid-deduplication.md](hybrid-deduplication.md).

## Configuration Sources

Runtime defaults are split across Python modules, Compose files, and `.env.example`. Compose values override Python fallbacks inside containers. When documenting or changing a setting, check all three locations; similarly named legacy “hybrid deduplication” variables are currently not read by Python.

## Recommended Reading Order

1. [README](../README.md)
2. [ARCHITECTURE_FLOW_API.md](ARCHITECTURE_FLOW_API.md)
3. [ARCHITECTURE_CACHE.md](ARCHITECTURE_CACHE.md)
4. [ARCHITECTURE_DATABASE.md](ARCHITECTURE_DATABASE.md)
5. [hybrid-deduplication.md](hybrid-deduplication.md)

Last reviewed against the code: 2026-06-30.
