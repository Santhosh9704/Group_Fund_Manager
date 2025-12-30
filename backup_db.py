import shutil
import os
from datetime import datetime
import time

# Configuration
SOURCE_DB = "database.db"
BACKUP_DIR = "backups"
MAX_BACKUPS = 30  # Keep last 30 days

def create_backup():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"database_backup_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    try:
        if os.path.exists(SOURCE_DB):
            shutil.copy2(SOURCE_DB, backup_path)
            print(f"✅ Backup created: {backup_path}")
            cleanup_old_backups()
        else:
            print(f"❌ Source database not found: {SOURCE_DB}")
    except Exception as e:
        print(f"❌ Backup failed: {e}")

def cleanup_old_backups():
    """Removes old backups to save space, keeping only the recent ones."""
    try:
        backups = sorted(
            [os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR) if f.startswith("database_backup_")],
            key=os.path.getmtime
        )
        
        while len(backups) > MAX_BACKUPS:
            oldest = backups.pop(0)
            os.remove(oldest)
            print(f"🗑️ Removed old backup: {oldest}")
            
    except Exception as e:
        print(f"⚠️ Cleanup failed: {e}")

if __name__ == "__main__":
    create_backup()
