"""
Migration script to add RFID cards table
Run this script to create the RFID cards table in the database
"""
from app.models.database import Base, engine, SessionLocal
from app.models.database import RFIDCard
from app.core.config import get_egypt_now

def create_rfid_cards_table():
    """Create RFID cards table"""
    print("Creating RFID cards table...")
    Base.metadata.create_all(bind=engine, tables=[RFIDCard.__table__])
    print("✅ RFID cards table created successfully!")

def add_test_rfid_cards():
    """Add some test RFID cards for testing"""
    db = SessionLocal()
    try:
        # Check if test cards already exist
        existing = db.query(RFIDCard).filter(RFIDCard.id_tag.in_(["TEST001", "TEST002", "TEST003"])).count()
        if existing > 0:
            print("Test RFID cards already exist. Skipping...")
            return
        
        test_cards = [
            RFIDCard(
                id_tag="TEST001",
                card_number="CARD001",
                holder_name="Test User 1",
                description="Test RFID card",
                is_active=True,
                is_blocked=False
            ),
            RFIDCard(
                id_tag="TEST002",
                card_number="CARD002",
                holder_name="Test User 2",
                description="Test RFID card",
                is_active=True,
                is_blocked=False
            ),
            RFIDCard(
                id_tag="TEST003",
                card_number="CARD003",
                holder_name="Blocked User",
                description="Blocked test card",
                is_active=True,
                is_blocked=True  # This card is blocked
            ),
            RFIDCard(
                id_tag="EXPIRED001",
                card_number="CARD004",
                holder_name="Expired User",
                description="Expired test card",
                is_active=True,
                is_blocked=False,
                expires_at=get_egypt_now().replace(year=2020)  # Expired card
            ),
        ]
        
        for card in test_cards:
            db.add(card)
        
        db.commit()
        print(f"✅ Added {len(test_cards)} test RFID cards!")
        print("   - TEST001: Active card")
        print("   - TEST002: Active card")
        print("   - TEST003: Blocked card")
        print("   - EXPIRED001: Expired card")
        
    except Exception as e:
        print(f"❌ Error adding test cards: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--test-data":
        print("Adding test RFID cards...")
        create_rfid_cards_table()
        add_test_rfid_cards()
    else:
        print("Creating RFID cards table...")
        create_rfid_cards_table()
        print("\nTo add test RFID cards, run:")
        print("  python migrate_add_rfid_cards.py --test-data")

