"""
Migration script to add wattage_limit and remaining_wattage fields to RFID cards table
Run this script to add the wattage management columns to the existing RFID cards table
"""
import sqlite3
from pathlib import Path
from app.core.config import settings

def migrate_add_wattage_fields():
    """Add wattage_limit and remaining_wattage columns to rfid_cards table"""
    # Get database path from settings
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    
    if not Path(db_path).exists():
        print(f"❌ Database file not found: {db_path}")
        print("   Please ensure the database exists before running this migration.")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(rfid_cards)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if "wattage_limit" in columns and "remaining_wattage" in columns:
            print("✅ Wattage fields already exist in rfid_cards table. Skipping migration.")
            conn.close()
            return True
        
        print("Adding wattage_limit and remaining_wattage columns to rfid_cards table...")
        
        # Add wattage_limit column
        if "wattage_limit" not in columns:
            cursor.execute("ALTER TABLE rfid_cards ADD COLUMN wattage_limit REAL")
            print("   ✅ Added wattage_limit column")
        
        # Add remaining_wattage column
        if "remaining_wattage" not in columns:
            cursor.execute("ALTER TABLE rfid_cards ADD COLUMN remaining_wattage REAL")
            print("   ✅ Added remaining_wattage column")
        
        # Initialize remaining_wattage for existing cards that have wattage_limit set
        cursor.execute("""
            UPDATE rfid_cards 
            SET remaining_wattage = wattage_limit 
            WHERE wattage_limit IS NOT NULL AND remaining_wattage IS NULL
        """)
        updated_count = cursor.rowcount
        if updated_count > 0:
            print(f"   ✅ Initialized remaining_wattage for {updated_count} existing cards")
        
        conn.commit()
        conn.close()
        
        print("✅ Migration completed successfully!")
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

if __name__ == "__main__":
    print("Running migration to add wattage fields to RFID cards table...")
    success = migrate_add_wattage_fields()
    if success:
        print("\nMigration completed successfully!")
    else:
        print("\nMigration failed. Please check the errors above.")
        exit(1)

