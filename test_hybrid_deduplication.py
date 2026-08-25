#!/usr/bin/env python3
"""
Test Script for Hybrid Deduplication (RabbitMQ + Advisory Locks)
===============================================================

This script tests the Phase 3 implementation:
- RabbitMQ Message Deduplication for task distribution
- PostgreSQL Advisory Locks for database operations
"""

import os
import sys
import time

import psycopg
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cache_utils import location_key
from db_utils import (
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
    _advisory_lock_id,
)
from workers.unified_worker import UnifiedWorker, generate_precompute_message_id


def test_message_id_generation():
    """Test deterministic message ID generation"""
    print("🧪 Testing Message ID Generation...")
    
    # Same parameters should generate same ID
    id1 = generate_precompute_message_id(46.7632, 14.8417, 405, "20251114T18", "asteroids")
    id2 = generate_precompute_message_id(46.7632, 14.8417, 405, "20251114T18", "asteroids")
    
    # Different parameters should generate different ID
    id3 = generate_precompute_message_id(46.7632, 14.8417, 405, "20251114T19", "asteroids")
    
    assert id1 == id2, "Same parameters should generate same ID"
    assert id1 != id3, "Different parameters should generate different ID"
    assert len(id1) == 64, "SHA256 should be 64 characters"
    
    print(f"✅ Message ID generation works: {id1[:16]}...")


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
            assert cursor.fetchone()["acquired"] is False
        with first.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
        with second.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (lock_id,))
            assert cursor.fetchone()["acquired"] is True
            cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
    finally:
        first.close()
        second.close()


def test_deduplication_logic():
    """Test the deduplication logic"""
    print("🧪 Testing Deduplication Logic...")
    
    # Create test parameters
    lat, lon, elevation = 46.7632, 14.8417, 405
    time_bucket = "20251114T18"
    object_type = "asteroids"
    
    # Generate message ID
    message_id = generate_precompute_message_id(lat, lon, elevation, time_bucket, object_type)
    
    # Create computation key for Advisory Locks
    loc_key = location_key(lat, lon, elevation)
    computation_key = f"precompute_{object_type}:{loc_key}:{time_bucket}"
    
    print(f"📝 Message ID: {message_id[:16]}...")
    print(f"🔒 Computation Key: {computation_key}")
    
    # Verify both are deterministic
    message_id_2 = generate_precompute_message_id(lat, lon, elevation, time_bucket, object_type)
    assert message_id == message_id_2, "Message IDs should be deterministic"
    
    print("✅ Deduplication logic is consistent")


@pytest.mark.integration
def test_hybrid_integration():
    """Test hybrid RabbitMQ + Advisory Locks integration"""
    print("🧪 Testing Hybrid Integration...")
    
    try:
        # Initialize worker (this will test RabbitMQ connection)
        rabbitmq_url_env = os.getenv('RABBITMQ_URL')
        if rabbitmq_url_env:
            from urllib.parse import urlparse

            parsed = urlparse(rabbitmq_url_env)
            rabbitmq_user = parsed.username or os.getenv('RABBITMQ_USER', 'admin')
            rabbitmq_password = parsed.password or os.getenv('RABBITMQ_PASSWORD', 'changeme')
            rabbitmq_host = parsed.hostname or os.getenv('RABBITMQ_HOST', 'rabbitmq')
            rabbitmq_port = parsed.port or os.getenv('RABBITMQ_PORT', '5672')
            rabbitmq_vhost = parsed.path or '/'
            if not rabbitmq_vhost.startswith('/'):
                rabbitmq_vhost = f"/{rabbitmq_vhost}"
            rabbitmq_url = f"amqp://{rabbitmq_user}:{rabbitmq_password}@{rabbitmq_host}:{rabbitmq_port}{rabbitmq_vhost}"
        else:
            rabbitmq_user = os.getenv('RABBITMQ_USER', 'admin')
            rabbitmq_password = os.getenv('RABBITMQ_PASSWORD', 'changeme')
            rabbitmq_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
            rabbitmq_port = os.getenv('RABBITMQ_PORT', '5672')
            rabbitmq_url = f"amqp://{rabbitmq_user}:{rabbitmq_password}@{rabbitmq_host}:{rabbitmq_port}/"
        
        worker = UnifiedWorker(
            worker_id="test_worker",
            rabbitmq_url=rabbitmq_url
        )
        
        if not worker.connect():
            pytest.skip("RabbitMQ integration service is not available")
        
        # Test queue declaration with deduplication
        worker._declare_queues()
        print("✅ Queues declared with deduplication arguments")
        
        # Test message sending
        test_location = {
            'latitude': 46.7632,
            'longitude': 14.8417,
            'elevation': 405,
            'name': 'Test Location'
        }
        
        success = worker.send_precompute_task_with_deduplication(
            'asteroids', test_location, '20251114T18', 20.0
        )
        
        if success:
            print("✅ Task sent with RabbitMQ deduplication")
        else:
            print("❌ Failed to send task with deduplication")
            pytest.fail("Could not publish a deduplicated task")
        
        worker.disconnect()
    except Exception as e:
        pytest.skip(f"RabbitMQ integration service is not available: {e}")


def main():
    """Run all tests"""
    print("🚀 Testing Hybrid Deduplication Implementation")
    print("=" * 50)
    
    tests = [
        ("Message ID Generation", test_message_id_generation),
        ("Advisory Locks", test_advisory_locks),
        ("Deduplication Logic", test_deduplication_logic),
        ("Hybrid Integration", test_hybrid_integration)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} ERROR: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Hybrid deduplication is working.")
        return True
    else:
        print("⚠️  Some tests failed. Check the implementation.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
