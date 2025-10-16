"""
Database models and initialization
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Boolean, Text, ForeignKey, JSON
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.sql import func
from datetime import datetime
import json

from app.core.config import settings

# Create database engine
engine = create_engine(settings.DATABASE_URL, echo=settings.DEBUG)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Charger(Base):
    """Charger/Charge Point model"""
    __tablename__ = "chargers"
    
    id = Column(String, primary_key=True, index=True)  # charger_id
    vendor = Column(String, nullable=True)
    model = Column(String, nullable=True)
    serial_number = Column(String, nullable=True)
    firmware_version = Column(String, nullable=True)
    
    # Status information
    status = Column(String, default="Unknown")  # Available, Charging, Faulted, Offline
    last_heartbeat = Column(DateTime, default=datetime.utcnow)
    last_message = Column(String, nullable=True)
    
    # Connection information
    is_connected = Column(Boolean, default=False)
    connection_time = Column(DateTime, nullable=True)
    disconnect_time = Column(DateTime, nullable=True)
    
    # Configuration
    configuration = Column(JSON, default=dict)
    
    # Retry configuration
    max_retries = Column(Integer, default=3)  # Maximum number of retry attempts
    retry_interval = Column(Integer, default=5)  # Retry interval in seconds
    retry_enabled = Column(Boolean, default=True)  # Enable/disable retry functionality
    
    # Site and organization
    site_id = Column(String, nullable=True)
    organization_id = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sessions = relationship("Session", back_populates="charger")
    connectors = relationship("Connector", back_populates="charger")
    messages = relationship("MessageLog", back_populates="charger")
    connection_events = relationship("ConnectionEvent", back_populates="charger")

class Connector(Base):
    """Connector model"""
    __tablename__ = "connectors"
    
    id = Column(Integer, primary_key=True, index=True)
    charger_id = Column(String, ForeignKey("chargers.id"), nullable=False)
    connector_id = Column(Integer, nullable=False)  # OCPP connector ID
    
    # Status
    status = Column(String, default="Available")  # Available, Occupied, Faulted, Unavailable
    error_code = Column(String, nullable=True)
    
    # Energy information
    energy_delivered = Column(Float, default=0.0)  # kWh
    power_delivered = Column(Float, default=0.0)   # kW
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    charger = relationship("Charger", back_populates="connectors")
    sessions = relationship("Session", back_populates="connector")

class Session(Base):
    """Charging session model"""
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, nullable=True)
    charger_id = Column(String, ForeignKey("chargers.id"), nullable=False)
    connector_id = Column(Integer, ForeignKey("connectors.id"), nullable=True)
    
    # User information
    id_tag = Column(String, nullable=True)
    user_id = Column(String, nullable=True)
    
    # Session timing
    start_time = Column(DateTime, default=datetime.utcnow)
    stop_time = Column(DateTime, nullable=True)
    duration = Column(Integer, nullable=True)  # seconds
    
    # Energy and cost
    energy_delivered = Column(Float, default=0.0)  # kWh
    cost = Column(Float, default=0.0)  # currency amount
    
    # Status
    status = Column(String, default="Active")  # Active, Completed, Stopped, Faulted
    
    # Meter values
    meter_start = Column(Float, nullable=True)
    meter_stop = Column(Float, nullable=True)
    
    # Additional data
    session_metadata = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    charger = relationship("Charger", back_populates="sessions")
    connector = relationship("Connector", back_populates="sessions")

class MessageLog(Base):
    """OCPP message logging"""
    __tablename__ = "message_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    charger_id = Column(String, ForeignKey("chargers.id"), nullable=False)
    
    # Message details
    message_type = Column(String, nullable=False)  # IN, OUT
    action = Column(String, nullable=False)  # BootNotification, Heartbeat, etc.
    message_id = Column(String, nullable=True)
    
    # Message content
    request = Column(Text, nullable=True)
    response = Column(Text, nullable=True)
    
    # Status
    status = Column(String, default="Success")  # Success, Error, Timeout
    
    # Timing
    timestamp = Column(DateTime, default=datetime.utcnow)
    processing_time = Column(Float, nullable=True)  # milliseconds
    
    # Relationships
    charger = relationship("Charger", back_populates="messages")

class SystemConfig(Base):
    """System configuration"""
    __tablename__ = "system_config"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ConnectionEvent(Base):
    """WebSocket connection event logging"""
    __tablename__ = "connection_events"
    
    id = Column(Integer, primary_key=True, index=True)
    charger_id = Column(String, ForeignKey("chargers.id"), nullable=False)
    
    # Event details
    event_type = Column(String, nullable=False)  # CONNECT, DISCONNECT, RECONNECT
    connection_id = Column(String, nullable=True)  # Unique connection identifier
    
    # Connection information
    remote_address = Column(String, nullable=True)  # Client IP address
    user_agent = Column(String, nullable=True)  # WebSocket user agent
    subprotocol = Column(String, nullable=True)  # OCPP subprotocol
    
    # Event metadata
    reason = Column(String, nullable=True)  # Disconnect reason, error message, etc.
    session_duration = Column(Integer, nullable=True)  # Connection duration in seconds
    
    # Additional data
    event_metadata = Column(JSON, default=dict)
    
    # Timestamps
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    charger = relationship("Charger", back_populates="connection_events")

class User(Base):
    """User model for authentication"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    # Roles and permissions
    roles = Column(JSON, default=list)  # ["admin", "operator", etc.]
    permissions = Column(JSON, default=list)
    
    # Organization
    organization_id = Column(String, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

# Database dependency
def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    
    # Create default system configurations
    db = SessionLocal()
    try:
        # Check if configurations already exist
        if not db.query(SystemConfig).filter(SystemConfig.key == "heartbeat_interval").first():
            default_configs = [
                SystemConfig(key="heartbeat_interval", value="60", description="Default heartbeat interval in seconds"),
                SystemConfig(key="meter_value_interval", value="60", description="Default meter value interval in seconds"),
                SystemConfig(key="connection_timeout", value="30", description="Connection timeout in seconds"),
                SystemConfig(key="max_retries", value="3", description="Maximum retry attempts for failed messages"),
                SystemConfig(key="retry_interval", value="5", description="Retry interval in seconds"),
            ]
            
            for config in default_configs:
                db.add(config)
            
            db.commit()
    finally:
        db.close()
