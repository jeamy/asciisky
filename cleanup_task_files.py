#!/usr/bin/env python3
"""
Cleanup-Script für Task-Worker Dateileichen
Erkennt und löscht verwaiste Task-Dateien basierend auf Alter und Status
"""
import os
import json
import glob
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

def find_task_files():
    """Finde alle Task- und Status-Dateien"""
    cache_dir = Path("cache")
    if not cache_dir.exists():
        return [], []

    task_files = list(cache_dir.glob("task_*.json"))
    status_files = list(cache_dir.glob("task_status_*.json"))

    return task_files, status_files

def extract_task_id(filepath):
    """Extrahiere Task-ID aus Dateiname"""
    filename = Path(filepath).name
    if filename.startswith("task_status_"):
        return filename[12:-5]  # Remove "task_status_" and ".json"
    elif filename.startswith("task_"):
        return filename[5:-5]   # Remove "task_" and ".json"
    return None

def get_file_age_hours(filepath):
    """Berechne Alter der Datei in Stunden"""
    try:
        mtime = os.path.getmtime(filepath)
        file_time = datetime.fromtimestamp(mtime, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - file_time).total_seconds() / 3600
    except Exception:
        return 0

def read_task_status(status_file):
    """Lese Task-Status aus Status-Datei"""
    try:
        with open(status_file, 'r') as f:
            return json.load(f)
    except Exception:
        return None

def analyze_task_files(dry_run=True, max_age_hours=24):
    """Analysiere Task-Dateien und identifiziere Dateileichen"""
    task_files, status_files = find_task_files()

    logger.info(f"Gefunden: {len(task_files)} Task-Dateien, {len(status_files)} Status-Dateien")

    # Gruppiere nach Task-ID
    task_ids = set()
    task_map = {}
    status_map = {}

    for task_file in task_files:
        task_id = extract_task_id(task_file)
        if task_id:
            task_ids.add(task_id)
            task_map[task_id] = task_file

    for status_file in status_files:
        task_id = extract_task_id(status_file)
        if task_id:
            task_ids.add(task_id)
            status_map[task_id] = status_file

    # Analysiere jeden Task
    orphaned_files = []
    completed_old_files = []
    error_old_files = []
    running_old_files = []

    for task_id in task_ids:
        task_file = task_map.get(task_id)
        status_file = status_map.get(task_id)

        # Berechne Alter
        task_age = get_file_age_hours(task_file) if task_file else 0
        status_age = get_file_age_hours(status_file) if status_file else 0
        max_age = max(task_age, status_age)

        # Lese Status
        status_data = read_task_status(status_file) if status_file else None
        status = status_data.get('status', 'unknown') if status_data else 'unknown'

        logger.info(f"\nTask {task_id}:")
        logger.info(f"  Task-Datei: {'✓' if task_file else '✗'} (Alter: {task_age:.1f}h)")
        logger.info(f"  Status-Datei: {'✓' if status_file else '✗'} (Alter: {status_age:.1f}h)")
        logger.info(f"  Status: {status}")
        logger.info(f"  Max-Alter: {max_age:.1f}h")

        # Kategorisiere
        if max_age > max_age_hours:
            if status == 'completed':
                # Erfolgreich abgeschlossen, aber Dateien nicht gelöscht
                completed_old_files.extend([f for f in [task_file, status_file] if f])
                logger.info(f"  → DATEILEICHE: Abgeschlossen aber nicht gelöscht")
            elif status == 'error':
                # Fehler, Dateien blieben zurück
                error_old_files.extend([f for f in [task_file, status_file] if f])
                logger.info(f"  → DATEILEICHE: Fehler-Task nicht bereinigt")
            elif status in ['running', 'starting']:
                # Läuft angeblich noch, aber zu alt
                running_old_files.extend([f for f in [task_file, status_file] if f])
                logger.info(f"  → DATEILEICHE: Hängender Task (läuft zu lange)")
            else:
                # Unbekannter Status oder verwaist
                orphaned_files.extend([f for f in [task_file, status_file] if f])
                logger.info(f"  → DATEILEICHE: Verwaist oder unbekannter Status")
        else:
            logger.info(f"  → OK: Noch jung genug")

    # Zusammenfassung
    all_orphaned = orphaned_files + completed_old_files + error_old_files + running_old_files

    logger.info(f"\n{'='*60}")
    logger.info("ZUSAMMENFASSUNG:")
    logger.info(f"Abgeschlossene alte Tasks: {len(completed_old_files)} Dateien")
    logger.info(f"Fehler-Tasks: {len(error_old_files)} Dateien")
    logger.info(f"Hängende Tasks: {len(running_old_files)} Dateien")
    logger.info(f"Verwaiste Dateien: {len(orphaned_files)} Dateien")
    logger.info(f"GESAMT zu löschende Dateien: {len(all_orphaned)}")

    if all_orphaned:
        logger.info(f"\nDateien älter als {max_age_hours}h:")
        for filepath in all_orphaned:
            age = get_file_age_hours(filepath)
            logger.info(f"  {filepath} (Alter: {age:.1f}h)")

        if not dry_run:
            logger.info(f"\nLösche {len(all_orphaned)} Dateien...")
            deleted = 0
            for filepath in all_orphaned:
                try:
                    os.remove(filepath)
                    deleted += 1
                    logger.info(f"  ✓ Gelöscht: {filepath}")
                except Exception as e:
                    logger.error(f"  ✗ Fehler beim Löschen {filepath}: {e}")
            logger.info(f"Erfolgreich gelöscht: {deleted}/{len(all_orphaned)} Dateien")
        else:
            logger.info(f"\nDRY-RUN: Würde {len(all_orphaned)} Dateien löschen")
            logger.info("Führe mit --delete aus, um tatsächlich zu löschen")

    return len(all_orphaned)

def main():
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    dry_run = True
    max_age_hours = 24

    if "--delete" in sys.argv:
        dry_run = False
        logger.warning("WARNUNG: Lösche tatsächlich Dateien!")

    if "--max-age" in sys.argv:
        try:
            idx = sys.argv.index("--max-age")
            max_age_hours = float(sys.argv[idx + 1])
        except Exception:
            logger.error("Fehler: --max-age benötigt eine Zahl")
            sys.exit(1)

    logger.info("Task-Dateien Cleanup")
    logger.info(f"Max-Alter: {max_age_hours} Stunden")
    logger.info(f"Modus: {'LÖSCHEN' if not dry_run else 'DRY-RUN'}")
    logger.info("="*60)

    orphaned_count = analyze_task_files(dry_run, max_age_hours)

    if orphaned_count == 0:
        logger.info("\n✓ Keine Dateileichen gefunden!")
    elif dry_run:
        logger.info(f"\n⚠ {orphaned_count} Dateileichen gefunden. Führe mit --delete aus zum Löschen.")

if __name__ == "__main__":
    main()
