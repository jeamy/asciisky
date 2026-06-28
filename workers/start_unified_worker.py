#!/usr/bin/env python3
"""
Unified Worker Start Script
==========================

Optimiertes Start-Skript für den Unified Worker mit:
- Environment-Konfiguration
- Health Checks
- Graceful Shutdown
"""

import os
import sys
import signal
import socket
import logging
from pathlib import Path

# Pfad anpassen für Imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from unified_worker import UnifiedWorker, wait_for_database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_worker_id() -> str:
    """Ermittle Worker ID aus Environment oder Hostname"""
    worker_id = os.getenv('WORKER_ID', '')

    # Fallback wenn nicht gesetzt oder Template nicht aufgelöst
    if not worker_id or '{{' in worker_id or '${' in worker_id:
        hostname = socket.gethostname()
        worker_id = f'unified-worker-{hostname}'

    return worker_id


def setup_environment():
    """Setup Environment mit Optimierungen"""
    # Worker-spezifische Defaults
    os.environ.setdefault('WORKER_MEMORY_LIMIT_MB', '512')
    os.environ.setdefault('WORKER_CPU_LIMIT_PERCENT', '80')


def check_system_resources():
    """Prüfe System-Ressourcen (optional, nur Warnung)"""
    try:
        import psutil

        memory = psutil.virtual_memory()
        cpu_count = psutil.cpu_count()

        logger.info(f"System: {cpu_count} CPUs, {memory.total / 1024 / 1024:.0f}MB RAM")

        if memory.available < 512 * 1024 * 1024:  # 512MB
            logger.warning(f"Low memory available: {memory.available / 1024 / 1024:.0f}MB")

    except ImportError:
        logger.debug("psutil not available - skipping resource check")
    except Exception as e:
        logger.debug(f"Resource check failed: {e}")


def main():
    """Hauptfunktion"""
    worker_id = get_worker_id()
    rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://admin:changeme@localhost:5672/')
    log_level = os.getenv('WORKER_LOG_LEVEL', 'INFO')

    # Logging Level setzen
    logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))

    logger.info("=" * 60)
    logger.info(f"Starting Unified Worker {worker_id}")
    logger.info(f"RabbitMQ: {rabbitmq_url}")
    logger.info("=" * 60)

    # Environment Setup
    setup_environment()

    # System Resources (nur Info)
    check_system_resources()

    # Warte auf Datenbank
    if not wait_for_database(worker_id):
        logger.error("Database not ready - exiting")
        sys.exit(1)

    # Worker erstellen und starten
    try:
        worker = UnifiedWorker(worker_id, rabbitmq_url)

        # Graceful Shutdown Handler
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum} - shutting down gracefully...")
            worker.stop()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # Worker starten
        worker.start()

    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
