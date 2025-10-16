#!/usr/bin/env python3
"""
Database migration script to add retry configuration columns to chargers table
Run this script on the server to update the database schema
"""

import sqlite3
import os
import sys
from datetime import datetime

def migrate_database():
    """Add retry configuration columns to chargers table"""
    
    # Database file path
    db_path = "ocpp_cms.db"
    
    if not os.path.exists(db_path):
        print(f"❌ Database file {db_path} not found!")
        return False
    
    print(f"🔧 Starting database migration for {db_path}")
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(chargers)")
        columns = [column[1] for column in cursor.fetchall()]
        
        print(f"📋 Current columns in chargers table: {columns}")
        
        # Add max_retries column if it doesn't exist
        if 'max_retries' not in columns:
            print("➕ Adding max_retries column...")
            cursor.execute("ALTER TABLE chargers ADD COLUMN max_retries INTEGER DEFAULT 3")
            print("✅ max_retries column added successfully")
        else:
            print("ℹ️  max_retries column already exists")
        
        # Add retry_interval column if it doesn't exist
        if 'retry_interval' not in columns:
            print("➕ Adding retry_interval column...")
            cursor.execute("ALTER TABLE chargers ADD COLUMN retry_interval INTEGER DEFAULT 5")
            print("✅ retry_interval column added successfully")
        else:
            print("ℹ️  retry_interval column already exists")
        
        # Add retry_enabled column if it doesn't exist
        if 'retry_enabled' not in columns:
            print("➕ Adding retry_enabled column...")
            cursor.execute("ALTER TABLE chargers ADD COLUMN retry_enabled BOOLEAN DEFAULT 1")
            print("✅ retry_enabled column added successfully")
        else:
            print("ℹ️  retry_enabled column already exists")
        
        # Update existing records with default values
        print("🔄 Updating existing records with default values...")
        cursor.execute("""
            UPDATE chargers 
            SET max_retries = 3, retry_interval = 5, retry_enabled = 1 
            WHERE max_retries IS NULL OR retry_interval IS NULL OR retry_enabled IS NULL
        """)
        updated_rows = cursor.rowcount
        print(f"✅ Updated {updated_rows} existing records")
        
        # Commit changes
        conn.commit()
        
        # Verify the changes
        cursor.execute("PRAGMA table_info(chargers)")
        columns_after = [column[1] for column in cursor.fetchall()]
        print(f"📋 Columns after migration: {columns_after}")
        
        # Check if all required columns exist
        required_columns = ['max_retries', 'retry_interval', 'retry_enabled']
        missing_columns = [col for col in required_columns if col not in columns_after]
        
        if missing_columns:
            print(f"❌ Migration failed! Missing columns: {missing_columns}")
            return False
        
        print("🎉 Database migration completed successfully!")
        print(f"📊 Added columns: {required_columns}")
        
        # Show sample data
        cursor.execute("SELECT id, max_retries, retry_interval, retry_enabled FROM chargers LIMIT 5")
        sample_data = cursor.fetchall()
        if sample_data:
            print("📋 Sample data after migration:")
            for row in sample_data:
                print(f"   Charger {row[0]}: max_retries={row[1]}, retry_interval={row[2]}, retry_enabled={row[3]}")
        
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("🚀 OCPP CMS Database Migration Script")
    print("=" * 50)
    print("📝 This script adds retry configuration columns to the chargers table")
    print("🔧 Required columns: max_retries, retry_interval, retry_enabled")
    print("=" * 50)
    
    success = migrate_database()
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("🔄 You can now restart the OCPP server")
        print("📋 The following columns were added to the chargers table:")
        print("   - max_retries (INTEGER, default: 3)")
        print("   - retry_interval (INTEGER, default: 5)")
        print("   - retry_enabled (BOOLEAN, default: 1)")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        print("🔍 Please check the error messages above and try again")
        sys.exit(1)
