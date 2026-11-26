"""Deduplication of precompute tasks: persistent task claims and advisory locks.

The publisher takes a claim per canonical task key (``precompute_task_claims``)
before it publishes; a worker holds a PostgreSQL advisory lock while it
computes one key.  The integration tests skip without PostgreSQL/RabbitMQ.
"""
import time
import uuid

import psycopg
import pytest

import settings
from api.rabbitmq.task_publisher import TaskPublisher
from db_utils import (
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
    _advisory_lock_id,
    release_precompute_task,
)
from workers.worker_utils import precompute_task_key

LOCATION = {"latitude": 46.7632, "longitude": 14.8417, "elevation": 405}


def _task(time_bucket: str, kind: str = "asteroids") -> dict:
    return {"kind": kind, "location": LOCATION, "time_bucket": time_bucket, "bucket_hours": 1}


def test_task_key_is_deterministic_and_bucketed():
    first = precompute_task_key(_task("2025-11-14T18:00:00+00:00"))
    same_bucket = precompute_task_key(_task("2025-11-14T18:59:00+00:00"))
    next_bucket = precompute_task_key(_task("2025-11-14T19:00:00+00:00"))
    comets = precompute_task_key(_task("2025-11-14T18:00:00+00:00", "comets"))

    assert first == same_bucket
    assert first != next_bucket
    assert first != comets
    # Elevation is normalized to 10 m steps.
    assert first.startswith("asteroids_46.7632_14.8417_410_")


def test_publisher_skips_an_already_claimed_task(monkeypatch):
    published = []
    publisher = TaskPublisher("amqp://test")
    monkeypatch.setattr("api.rabbitmq.task_publisher.claim_precompute_task", lambda _key: False)
    monkeypatch.setattr(publisher, "_publish", lambda *args: published.append(args))

    task_id = publisher.publish_precompute_task("asteroids", LOCATION, "2025-11-14T18:00:00+00:00")

    assert task_id.startswith("asteroids_")
    assert published == []


@pytest.mark.integration
def test_advisory_locks():
    """Verify real lock contention using two independent DB sessions."""
    computation_key = f"test_computation:{int(time.time())}"
    connection_args = {
        "host": POSTGRES_HOST,
        "port": POSTGRES_PORT,
        "dbname": POSTGRES_DB,
        "user": POSTGRES_USER,
        "password": POSTGRES_PASSWORD,
        "autocommit": True,
    }
    try:
        first = psycopg.connect(**connection_args)
        second = psycopg.connect(**connection_args)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL integration service is not available")
    try:
        lock_id = _advisory_lock_id(computation_key)
        with first.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
        with second.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (lock_id,))
            assert cursor.fetchone()[0] is False
        with first.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
        with second.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (lock_id,))
            assert cursor.fetchone()[0] is True
            cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
    finally:
        first.close()
        second.close()


@pytest.mark.integration
def test_publisher_publishes_once_per_claim():
    """Two publications of one key reach the broker once (needs PostgreSQL and RabbitMQ)."""
    # A bucket far in the past keeps the test task apart from real ones.
    time_bucket = f"1999-01-01T{uuid.uuid4().int % 24:02d}:00:00+00:00"
    task = _task(time_bucket)
    publisher = TaskPublisher(settings.RABBITMQ_URL)
    published = []
    original = publisher._publish

    def counting_publish(*args):
        published.append(args)
        return original(*args)

    publisher._publish = counting_publish
    try:
        publisher.publish_precompute_task("asteroids", LOCATION, time_bucket)
        publisher.publish_precompute_task("asteroids", LOCATION, time_bucket)
    except Exception as exc:
        pytest.skip(f"PostgreSQL/RabbitMQ integration services are not available: {exc}")
    finally:
        try:
            release_precompute_task(precompute_task_key(task))
        except Exception:
            pass
        publisher.close()

    assert len(published) == 1
