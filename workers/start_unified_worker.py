#!/usr/bin/env python3
"""
Unified Worker Start Script
==========================

Optimiertes Start-Skript für den Unified Worker mit:
- Environment-Konfiguration
- Health Checks
- Graceful Shutdown
- Performance-Monitoring
"""

import os
import sys
import time
import signal
import socket
import logging
import argparse
from pathlib import Path

# Pfad anpassen für Imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))  # For worker modules

from unified_worker import UnifiedWorker, wait_for_database
from config.interpolation_config import get_interpolation_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_arguments():
    """Parse Kommandozeilen-Argumente"""
    # Default Worker ID mit Hostname
    default_worker_id = os.getenv('WORKER_ID', '')
    # Fallback wenn nicht gesetzt, Docker Swarm Template oder Shell-Variable nicht aufgelöst
    if not default_worker_id or '{{' in default_worker_id or '${' in default_worker_id:
        # Fallback: Verwende tatsächlichen Hostname
        hostname = socket.gethostname()
        default_worker_id = f'unified-worker-{hostname}'
    
    parser = argparse.ArgumentParser(description='Start Unified Worker')
    parser.add_argument('--worker-id', type=str, 
                       default=default_worker_id,
                       help='Worker ID')
    parser.add_argument('--rabbitmq-url', type=str,
                       default=os.getenv('RABBITMQ_URL', 'amqp://admin:changeme@localhost:5672/'),
                       help='RabbitMQ URL')
    parser.add_argument('--worker-type', type=str, choices=['unified', 'precompute', 'on_demand'],
                       default='unified',
                       help='Worker Typ')
    parser.add_argument('--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default=os.getenv('WORKER_LOG_LEVEL', 'INFO'),
                       help='Log Level')
    parser.add_argument('--prefetch-count', type=int,
                       default=int(os.getenv('RABBITMQ_PREFETCH_COUNT', '2')),
                       help='RabbitMQ Prefetch Count')
    
    return parser.parse_args()


def setup_environment():
    """Setup Environment mit Optimierungen"""
    # Python Optimierungen
    os.environ['PYTHONOPTIMIZE'] = '2'  # Byte-Code Optimierung
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'  # Keine .pyc Dateien
    
    # Worker-spezifische Environment Variablen
    os.environ['WORKER_MEMORY_LIMIT_MB'] = os.getenv('WORKER_MEMORY_LIMIT_MB', '512')
    os.environ['WORKER_CPU_LIMIT_PERCENT'] = os.getenv('WORKER_CPU_LIMIT_PERCENT', '80')
    
    # Smart Interpolation Konfiguration
    config = get_interpolation_config()
    logger.info(f"Smart Interpolation enabled: {config.enable_smart_interpolation}")
    logger.info(f"Interpolation strategy: {config.interpolation_strategy.value}")
    
    return config


def check_system_requirements():
    """Prüfe System-Anforderungen"""
    try:
        import psutil
        
        # Memory Check
        memory = psutil.virtual_memory()
        if memory.available < 1024 * 1024 * 1024:  # 1GB
            logger.warning(f"Low memory available: {memory.available / 1024 / 1024:.1f}MB")
        
        # CPU Check
        cpu_count = psutil.cpu_count()
        logger.info(f"System: {cpu_count} CPUs, {memory.total / 1024 / 1024:.1f}MB RAM")
        
        # Disk Space Check
        disk = psutil.disk_usage('/')
        if disk.free < 1024 * 1024 * 1024:  # 1GB
            logger.warning(f"Low disk space: {disk.free / 1024 / 1024:.1f}MB")
        
        return True
        
    except ImportError:
        logger.warning("psutil not available - cannot check system requirements")
        return True
    except Exception as e:
        logger.error(f"Error checking system requirements: {e}")
        return False


def main():
    """Hauptfunktion"""
    args = parse_arguments()
    
    # Logging Level setzen
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    logger.info("=" * 60)
    logger.info(f"Starting Unified Worker {args.worker_id}")
    logger.info(f"Type: {args.worker_type}")
    logger.info(f"RabbitMQ: {args.rabbitmq_url}")
    logger.info(f"Prefetch Count: {args.prefetch_count}")
    logger.info("=" * 60)
    
    # Environment Setup
    config = setup_environment()
    
    # System Requirements prüfen
    if not check_system_requirements():
        logger.error("System requirements not met - exiting")
        sys.exit(1)
    
    # Warte auf Datenbank
    if not wait_for_database(args.worker_id):
        logger.error("Database not ready - exiting")
        sys.exit(1)
    
    # Worker erstellen und starten
    try:
        worker = UnifiedWorker(args.worker_id, args.rabbitmq_url)
        
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
