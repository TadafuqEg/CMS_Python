# Database Migration Guide

## Migration Script: `migrate_add_retry_columns.py`

This script adds retry configuration columns to the `chargers` table in the OCPP CMS database.

### What it does:
- Adds `max_retries` column (INTEGER, default: 3)
- Adds `retry_interval` column (INTEGER, default: 5) 
- Adds `retry_enabled` column (BOOLEAN, default: 1)
- Updates existing records with default values

### How to run on server:

1. **Stop the OCPP server** (if running):
   ```bash
   # Find and kill the Python process
   ps aux | grep python
   kill <process_id>
   ```

2. **Run the migration script**:
   ```bash
   python migrate_add_retry_columns.py
   ```

3. **Expected output**:
   ```
   🚀 OCPP CMS Database Migration Script
   ==================================================
   🔧 Starting database migration for ocpp_cms.db
   📋 Current columns in chargers table: [...]
   ➕ Adding max_retries column...
   ✅ max_retries column added successfully
   ➕ Adding retry_interval column...
   ✅ retry_interval column added successfully
   ➕ Adding retry_enabled column...
   ✅ retry_enabled column added successfully
   🔄 Updating existing records with default values...
   ✅ Updated X existing records
   🎉 Database migration completed successfully!
   ```

4. **Restart the OCPP server**:
   ```bash
   python run_fastapi.py
   ```

### Safety features:
- ✅ Checks if columns already exist before adding them
- ✅ Safe to run multiple times
- ✅ Updates existing records with default values
- ✅ Verifies migration success
- ✅ Shows sample data after migration

### Troubleshooting:
- If you get "database is locked" error, make sure the OCPP server is stopped
- If migration fails, check the error messages and ensure you have write permissions to the database file
- The script will show which columns already exist vs. which ones were added
