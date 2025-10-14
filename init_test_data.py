from sqlalchemy.orm import Session
from app.models.database import SessionLocal, Charger, Connector
from datetime import datetime, timezone

def init_test_data():
    db = SessionLocal()
    try:
        # Add Charger
        charger = db.query(Charger).filter(Charger.id == "CP001").first()
        if not charger:
            charger = Charger(
                id="CP001",
                status="Available",
                is_connected=True,
                last_heartbeat=datetime.now(timezone.UTC),
                configuration={}
            )
            db.add(charger)
            db.commit()
            print(f"Added charger CP001")

        # Add Connector
        connector = db.query(Connector).filter(
            Connector.charger_id == "CP001",
            Connector.connector_id == 1
        ).first()
        if not connector:
            connector = Connector(
                charger_id="CP001",
                connector_id=1,
                status="Available",
                error_code=None,
                energy_delivered=0.0,
                power_delivered=0.0
            )
            db.add(connector)
            db.commit()
            print(f"Added connector 1 for CP001")
    except Exception as e:
        print(f"Error adding test data: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_test_data()