#!/usr/bin/env python3
"""
Nightly Data Updater
Downloads and processes asteroid/comet data once per day at 2:00 AM
"""
import os
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from ftplib import FTP, FTP_TLS

from data_paths import COMET_ELEMENTS_PATH, MPCORB_PATH, ensure_data_dirs

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [NIGHTLY-UPDATE] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration
UPDATE_HOUR = int(os.environ.get('ASCII_SKY_UPDATE_HOUR', '2'))  # 2:00 AM default
CHECK_INTERVAL_SECONDS = 60 * 30  # Check every 30 minutes

# Track last update date
LAST_UPDATE_FILE = Path('cache/last_data_update.txt')


def env_flag(name, default=False):
    """Parse common truthy/falsey env flag values."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def get_env_value(*names, default=None):
    """Return the first non-empty environment value from the provided names."""
    for name in names:
        value = os.environ.get(name)
        if value is not None and value != '':
            return value
    return default


def ftp_download_enabled():
    """FTP is enabled by default and can be disabled per host via FTP_DISABLED=true."""
    return not env_flag('FTP_DISABLED', default=False)


def download_file_from_ftp(remote_name, local_path):
    """Download a single file from the configured FTP/FTPS server."""
    ftp_host = get_env_value('FTP_SERVER', 'FTP_HOST')
    ftp_user = get_env_value('FTP_USER', 'FTP_USERNAME', default='anonymous')
    ftp_password = get_env_value('FTP_PASSWD', 'FTP_PASSWORD', default='')
    ftp_port = int(get_env_value('FTP_PORT', default='21'))
    ftp_scheme = get_env_value('FTP_SCHEME', default='ftp').strip().lower()
    ftp_upload = get_env_value('FTP_UPLOAD', default='').strip().strip('/')

    if not ftp_host:
        raise RuntimeError("FTP download is enabled, but FTP_SERVER is not configured")

    remote_path = f"{ftp_upload}/{remote_name}" if ftp_upload else remote_name
    local_target = Path(local_path)
    local_target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = local_target.with_suffix(local_target.suffix + '.part')

    ftp_class = FTP_TLS if ftp_scheme == 'ftps' else FTP
    logger.info(f"Downloading {remote_name} from {ftp_scheme}://{ftp_host}:{ftp_port}/{remote_path}")

    with ftp_class() as ftp:
        ftp.connect(ftp_host, ftp_port, timeout=300)
        ftp.login(ftp_user, ftp_password)
        if ftp_scheme == 'ftps':
            ftp.prot_p()
        with temp_target.open('wb') as out_file:
            ftp.retrbinary(f"RETR {remote_path}", out_file.write)

    temp_target.replace(local_target)
    logger.info(f"✓ Downloaded {remote_name} to {local_target}")
    return local_target


def get_last_update_date():
    """Get the date of the last successful update"""
    if LAST_UPDATE_FILE.exists():
        try:
            with open(LAST_UPDATE_FILE, 'r') as f:
                date_str = f.read().strip()
                return datetime.fromisoformat(date_str).date()
        except Exception:
            pass
    return None


def set_last_update_date(date):
    """Record the date of successful update"""
    LAST_UPDATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LAST_UPDATE_FILE, 'w') as f:
        f.write(date.isoformat())


def should_update_now():
    """Check if it's time to update (2 AM and not updated today)"""
    now = datetime.now()
    today = now.date()
    
    # Check if already updated today
    last_update = get_last_update_date()
    if last_update == today:
        return False
    
    # Check if it's the right hour (2 AM by default)
    if now.hour != UPDATE_HOUR:
        return False
    
    return True


def update_asteroid_data():
    """Download and process asteroid data"""
    logger.info("Updating asteroid data...")
    try:
        import gzip
        import pickle
        import pandas as pd
        from pathlib import Path
        from skyfield.data import mpc
        from db_utils import store_asteroid_dataframe, get_database_stats
        import bright_asteroids
        
        # Download latest data
        ensure_data_dirs()
        mpcorb_file = Path(MPCORB_PATH)
        if ftp_download_enabled():
            download_file_from_ftp('MPCORB.DAT.gz', mpcorb_file)
        elif bright_asteroids.download_mpcorb_file():
            logger.info("✓ Downloaded latest MPCORB.DAT")
        else:
            logger.error("✗ Failed to download asteroid data")
            return False
        
        # Load and parse
        with gzip.open(mpcorb_file, 'rb') as f:
            df = mpc.load_mpcorb_dataframe(f)
        
        logger.info(f"✓ Loaded {len(df)} asteroids from MPCORB.DAT")
        
        # Convert types
        numeric_cols = [
            'magnitude_H', 'magnitude_G', 'mean_anomaly_degrees', 'argument_of_perihelion_degrees',
            'longitude_of_ascending_node_degrees', 'inclination_degrees', 'eccentricity',
            'mean_daily_motion_degrees', 'semimajor_axis_au'
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df['magnitude_G'] = df['magnitude_G'].fillna(0.15)
        
        # Store in database (as pickle)
        df_pickle = pickle.dumps(df)
        store_asteroid_dataframe(df_pickle)
        logger.info(f"✓ Stored asteroid DataFrame in PostgreSQL")
        
        # Verify
        stats = get_database_stats()
        logger.info(f"✓ Database now contains {stats['asteroids_count']} asteroids")
        return True
            
    except Exception as e:
        logger.error(f"✗ Error updating asteroid data: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def update_comet_data():
    """Download and process comet data"""
    logger.info("Updating comet data...")
    try:
        import pickle
        from db_utils import get_database_stats, store_comet_dataframe
        import comets

        ensure_data_dirs()
        if ftp_download_enabled():
            download_file_from_ftp('COMET_ELEMENTS.txt', COMET_ELEMENTS_PATH)

        # Load from file (comets.py handles direct MPC download when FTP is disabled)
        df = comets.load_comet_dataframe(use_cache=False)
        
        if df is not None and not df.empty:
            logger.info(f"✓ Loaded {len(df)} comets from CometEls.txt")
            
            # Store in database (as pickle)
            df_pickle = pickle.dumps(df)
            store_comet_dataframe(df_pickle)
            logger.info(f"✓ Stored comet DataFrame in PostgreSQL")
            
            # Verify
            stats = get_database_stats()
            logger.info(f"✓ Database now contains {stats['comets_count']} comets")
            return True
        else:
            logger.error("✗ Failed to load comet data")
            return False
            
    except Exception as e:
        logger.error(f"✗ Error updating comet data: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def perform_nightly_update():
    """Perform the complete nightly update"""
    logger.info("=" * 80)
    logger.info(f"Starting nightly data update at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    
    success = True
    
    # Update asteroids
    if not update_asteroid_data():
        success = False
    
    # Update comets
    if not update_comet_data():
        success = False
    
    if success:
        # Record successful update
        set_last_update_date(datetime.now().date())
        logger.info("=" * 80)
        logger.info("✓ Nightly update completed successfully")
        logger.info("=" * 80)
    else:
        logger.error("=" * 80)
        logger.error("✗ Nightly update completed with errors")
        logger.error("=" * 80)
    
    return success


def run_update_loop():
    """Main loop: check every 30 minutes if update is needed"""
    logger.info("Nightly Data Updater started")
    logger.info(f"Update time: {UPDATE_HOUR}:00 (local time)")
    logger.info(f"Check interval: {CHECK_INTERVAL_SECONDS}s")
    logger.info("=" * 80)
    
    while True:
        try:
            if should_update_now():
                perform_nightly_update()
            else:
                now = datetime.now()
                last_update = get_last_update_date()
                logger.debug(f"Check at {now.strftime('%H:%M')} - No update needed (last: {last_update})")
            
            # Wait before next check
            time.sleep(CHECK_INTERVAL_SECONDS)
            
        except KeyboardInterrupt:
            logger.info("Shutting down nightly updater...")
            break
        except Exception as e:
            logger.error(f"Error in update loop: {e}")
            time.sleep(CHECK_INTERVAL_SECONDS)


def check_initial_data():
    """Check if database has data, if not perform initial update"""
    try:
        from db_utils import get_asteroid_dataframe, get_comet_dataframe
        
        asteroid_df = get_asteroid_dataframe()
        comet_df = get_comet_dataframe()
        
        if not asteroid_df and not comet_df:
            logger.info("=" * 80)
            logger.info("Database is empty - performing initial data load")
            logger.info("=" * 80)
            perform_nightly_update()
            return True
        else:
            logger.info("Database has data - skipping initial load")
            return False
    except Exception as e:
        logger.warning(f"Could not check database status: {e}")
        logger.info("Performing initial data load to be safe")
        perform_nightly_update()
        return True


if __name__ == "__main__":
    # Allow manual trigger
    if len(sys.argv) > 1 and sys.argv[1] == "--now":
        logger.info("Manual update triggered")
        perform_nightly_update()
    else:
        # Check if initial data load is needed
        check_initial_data()
        # Then start regular update loop
        run_update_loop()
