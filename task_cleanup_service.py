#!/usr/bin/env python3
"""
Automatischer Cleanup-Service für Task-Worker Dateileichen
Läuft kontinuierlich und bereinigt alte Task-Dateien
"""
import os
import time
import logging
from datetime import datetime, timezone
from cleanup_task_files import analyze_task_files

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def cleanup_cycle():
    """Führe einen Cleanup-Zyklus durch"""
    try:
        # Cleanup-Parameter aus Umgebungsvariablen
        max_age_hours = float(os.environ.get("ASCII_SKY_TASK_CLEANUP_HOURS", "6"))
        
        logger.info(f"Starting cleanup cycle (max_age: {max_age_hours}h)")
        
        # Führe Cleanup durch (nicht dry-run)
        orphaned_count = analyze_task_files(dry_run=False, max_age_hours=max_age_hours)
        
        if orphaned_count > 0:
            logger.info(f"Cleaned up {orphaned_count} orphaned task files")
        else:
            logger.debug("No orphaned files found")
            
    except Exception as e:
        logger.error(f"Error during cleanup cycle: {e}")

def main():
    """Hauptschleife des Cleanup-Services"""
    # Cleanup-Intervall aus Umgebungsvariable (Standard: 1 Stunde)
    cleanup_interval_minutes = int(os.environ.get("ASCII_SKY_TASK_CLEANUP_INTERVAL", "60"))
    
    logger.info("Task cleanup service starting...")
    logger.info(f"Cleanup interval: {cleanup_interval_minutes} minutes")
    
    # Führe initial einen Cleanup durch
    cleanup_cycle()
    
    # Dann regelmäßig
    while True:
        try:
            time.sleep(cleanup_interval_minutes * 60)
            cleanup_cycle()
        except KeyboardInterrupt:
            logger.info("Cleanup service stopped by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            # Warte 5 Minuten bei Fehlern, um tight loops zu vermeiden
            time.sleep(300)

if __name__ == "__main__":
    main()
