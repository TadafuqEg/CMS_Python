"""
Charger management endpoints
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from pydantic import BaseModel

from app.models.database import get_db, Charger, Connector, Session as DBSession
from app.services.session_manager import SessionManager

router = APIRouter()

# Pydantic models for request/response
class ChargerResponse(BaseModel):
    id: str
    vendor: Optional[str]
    model: Optional[str]
    serial_number: Optional[str]
    firmware_version: Optional[str]
    status: str
    last_heartbeat: Optional[datetime]
    last_message: Optional[str]
    is_connected: bool
    connection_time: Optional[datetime]
    site_id: Optional[str]
    organization_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    connectors: Optional[List[Dict[str, Any]]] = []

class ChargerDetailResponse(ChargerResponse):
    configuration: Dict[str, Any]
    connectors: List[Dict[str, Any]]
    active_sessions: int
    total_sessions: int
    energy_delivered_today: float

class ChargerUpdateRequest(BaseModel):
    site_id: Optional[str] = None
    organization_id: Optional[str] = None
    configuration: Optional[Dict[str, Any]] = None

class ChargerCreateRequest(BaseModel):
    id: str
    vendor: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    site_id: Optional[str] = None
    organization_id: Optional[str] = None

@router.get("/chargers/ids")
async def get_charger_ids(db: Session = Depends(get_db)):
    """Get a list of all charger IDs"""
    chargers = db.query(Charger.id).all()
    return [c.id for c in chargers]

@router.get("/chargers", response_model=List[ChargerResponse])
async def get_chargers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get list of chargers with optional filtering"""
    
    query = db.query(Charger)
    
    # Apply filters
    if status:
        query = query.filter(Charger.status == status)
    if site_id:
        query = query.filter(Charger.site_id == site_id)
    if organization_id:
        query = query.filter(Charger.organization_id == organization_id)
    
    # Apply pagination and ordering
    chargers = query.order_by(desc(Charger.last_heartbeat)).offset(skip).limit(limit).all()
    
    # Get charger IDs for efficient connector querying
    charger_ids = [charger.id for charger in chargers]
    
    # Fetch all connectors for these chargers in one query (optimize N+1 problem)
    connectors_dict = {}
    if charger_ids:
        connectors = db.query(Connector).filter(Connector.charger_id.in_(charger_ids)).all()
        # Group connectors by charger_id
        for conn in connectors:
            if conn.charger_id not in connectors_dict:
                connectors_dict[conn.charger_id] = []
            connectors_dict[conn.charger_id].append({
                "id": conn.id,
                "connector_id": conn.connector_id,
                "status": conn.status,
                "error_code": conn.error_code,
                "energy_delivered": conn.energy_delivered,
                "power_delivered": conn.power_delivered
            })
    
    # Build response with connectors for each charger
    result = []
    for charger in chargers:
        # Get connectors for this charger (empty list if none)
        connector_data = connectors_dict.get(charger.id, [])
        
        # Create ChargerResponse with connectors
        charger_response = ChargerResponse(
            id=charger.id,
            vendor=charger.vendor,
            model=charger.model,
            serial_number=charger.serial_number,
            firmware_version=charger.firmware_version,
            status=charger.status,
            last_heartbeat=charger.last_heartbeat,
            last_message=charger.last_message,
            is_connected=charger.is_connected,
            connection_time=charger.connection_time,
            site_id=charger.site_id,
            organization_id=charger.organization_id,
            created_at=charger.created_at,
            updated_at=charger.updated_at,
            connectors=connector_data
        )
        result.append(charger_response)
    
    return result

@router.get("/chargers/{charger_id}", response_model=ChargerDetailResponse)
async def get_charger_detail(charger_id: str, db: Session = Depends(get_db)):
    """Get detailed information about a specific charger"""
    
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    # Get connectors
    connectors = db.query(Connector).filter(Connector.charger_id == charger_id).all()
    connector_data = [
        {
            "id": conn.id,
            "connector_id": conn.connector_id,
            "status": conn.status,
            "error_code": conn.error_code,
            "energy_delivered": conn.energy_delivered,
            "power_delivered": conn.power_delivered
        }
        for conn in connectors
    ]
    
    # Get session statistics
    active_sessions = db.query(DBSession).filter(
        DBSession.charger_id == charger_id,
        DBSession.status == "Active"
    ).count()
    
    total_sessions = db.query(DBSession).filter(DBSession.charger_id == charger_id).count()
    
    # Get energy delivered today
    today = datetime.utcnow().date()
    energy_today = db.query(func.sum(DBSession.energy_delivered)).filter(
        DBSession.charger_id == charger_id,
        func.date(DBSession.stop_time) == today
    ).scalar() or 0.0
    
    return ChargerDetailResponse(
        id=charger.id,
        vendor=charger.vendor,
        model=charger.model,
        serial_number=charger.serial_number,
        firmware_version=charger.firmware_version,
        status=charger.status,
        last_heartbeat=charger.last_heartbeat,
        last_message=charger.last_message,
        is_connected=charger.is_connected,
        connection_time=charger.connection_time,
        site_id=charger.site_id,
        organization_id=charger.organization_id,
        created_at=charger.created_at,
        updated_at=charger.updated_at,
        configuration=charger.configuration or {},
        connectors=connector_data,
        active_sessions=active_sessions,
        total_sessions=total_sessions,
        energy_delivered_today=float(energy_today)
    )

@router.put("/chargers/{charger_id}")
async def update_charger(
    charger_id: str,
    update_data: ChargerUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update charger information"""
    
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    # Update fields
    if update_data.site_id is not None:
        charger.site_id = update_data.site_id
    if update_data.organization_id is not None:
        charger.organization_id = update_data.organization_id
    if update_data.configuration is not None:
        charger.configuration = update_data.configuration
    
    charger.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(charger)
    
    return {"message": "Charger updated successfully", "charger_id": charger_id}

@router.delete("/chargers/{charger_id}")
async def delete_charger(charger_id: str, db: Session = Depends(get_db)):
    """Delete a charger (force disconnect)"""
    
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    # Mark as disconnected
    charger.is_connected = False
    charger.status = "Offline"
    charger.disconnect_time = datetime.utcnow()
    charger.updated_at = datetime.utcnow()
    
    db.commit()
    
    # TODO: Actually disconnect the WebSocket connection
    # This would require access to the WebSocket manager
    
    return {"message": f"Charger {charger_id} disconnected successfully"}

@router.get("/chargers/{charger_id}/sessions")
async def get_charger_sessions(
    charger_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get sessions for a specific charger"""
    
    # Verify charger exists
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    query = db.query(DBSession).filter(DBSession.charger_id == charger_id)
    
    if status:
        query = query.filter(DBSession.status == status)
    
    sessions = query.order_by(desc(DBSession.start_time)).offset(skip).limit(limit).all()
    
    return [
        {
            "id": session.id,
            "transaction_id": session.transaction_id,
            "connector_id": session.connector_id,
            "id_tag": session.id_tag,
            "user_id": session.user_id,
            "start_time": session.start_time,
            "stop_time": session.stop_time,
            "duration": session.duration,
            "energy_delivered": session.energy_delivered,
            "cost": session.cost,
            "status": session.status,
            "meter_start": session.meter_start,
            "meter_stop": session.meter_stop
        }
        for session in sessions
    ]

@router.get("/chargers/{charger_id}/statistics")
async def get_charger_statistics(
    charger_id: str,
    days: int = Query(7, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """Get statistics for a specific charger"""
    
    # Verify charger exists
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Get session statistics
    sessions = db.query(DBSession).filter(
        DBSession.charger_id == charger_id,
        DBSession.start_time >= start_date
    ).all()
    
    # Calculate metrics
    total_sessions = len(sessions)
    completed_sessions = len([s for s in sessions if s.status == "Completed"])
    total_energy = sum(s.energy_delivered or 0 for s in sessions)
    total_cost = sum(s.cost or 0 for s in sessions)
    total_duration = sum(s.duration or 0 for s in sessions)
    
    # Daily breakdown
    daily_stats = {}
    for session in sessions:
        date_key = session.start_time.date().isoformat()
        if date_key not in daily_stats:
            daily_stats[date_key] = {
                "sessions": 0,
                "energy": 0.0,
                "cost": 0.0,
                "duration": 0
            }
        
        daily_stats[date_key]["sessions"] += 1
        daily_stats[date_key]["energy"] += session.energy_delivered or 0
        daily_stats[date_key]["cost"] += session.cost or 0
        daily_stats[date_key]["duration"] += session.duration or 0
    
    return {
        "charger_id": charger_id,
        "period_days": days,
        "total_sessions": total_sessions,
        "completed_sessions": completed_sessions,
        "total_energy_kwh": total_energy,
        "total_cost": total_cost,
        "total_duration_seconds": total_duration,
        "average_session_duration": total_duration / total_sessions if total_sessions > 0 else 0,
        "average_energy_per_session": total_energy / total_sessions if total_sessions > 0 else 0,
        "daily_breakdown": daily_stats
    }

@router.post("/chargers")
async def add_charger(
    charger: ChargerCreateRequest,
    db: Session = Depends(get_db)
):
    """Add a new charger"""
    if not charger.id or charger.id.strip() == "":
        raise HTTPException(status_code=400, detail="Charger id must not be empty")
    existing = db.query(Charger).filter(Charger.id == charger.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Charger with this id already exists")
    new_charger = Charger(
        id=charger.id,
        vendor=charger.vendor,
        model=charger.model,
        serial_number=charger.serial_number,
        firmware_version=charger.firmware_version,
        site_id=charger.site_id,
        organization_id=charger.organization_id,
        status="Offline",
        is_connected=False
    )
    db.add(new_charger)
    db.commit()
    db.refresh(new_charger)
    return {"message": "Charger added successfully", "charger_id": new_charger.id}

@router.post("/chargers/cleanup_empty")
async def cleanup_empty_chargers(db: Session = Depends(get_db)):
    """Delete chargers with empty or whitespace-only IDs"""
    deleted = db.query(Charger).filter((Charger.id == "") | (Charger.id == None) | (Charger.id == " ")).delete(synchronize_session=False)
    db.commit()
    return {"message": f"Deleted {deleted} chargers with empty IDs."}
