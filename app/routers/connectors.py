"""
Connector management endpoints
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from pydantic import BaseModel, Field

from app.models.database import get_db, Connector, Charger

router = APIRouter()

# Pydantic models for request/response
class ConnectorResponse(BaseModel):
    id: int
    charger_id: str
    connector_id: int
    status: str
    error_code: Optional[str]
    energy_delivered: float
    power_delivered: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ConnectorCreateRequest(BaseModel):
    charger_id: str = Field(..., description="ID of the charger this connector belongs to")
    connector_id: int = Field(..., ge=0, description="OCPP connector ID (0 for whole charging point, >=1 for specific connector)")
    status: Optional[str] = Field(default="Available", description="Initial status of the connector")
    error_code: Optional[str] = Field(default=None, description="Error code if applicable")

class ConnectorUpdateRequest(BaseModel):
    status: Optional[str] = Field(None, description="Status of the connector")
    error_code: Optional[str] = Field(None, description="Error code if applicable")
    energy_delivered: Optional[float] = Field(None, ge=0, description="Total energy delivered in kWh")
    power_delivered: Optional[float] = Field(None, ge=0, description="Current power delivered in kW")

class ConnectorDetailResponse(ConnectorResponse):
    charger: Optional[dict] = None

@router.post("/connectors", response_model=ConnectorResponse, status_code=201)
async def create_connector(
    connector: ConnectorCreateRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new connector for a charger
    
    - **charger_id**: ID of the charger
    - **connector_id**: OCPP connector ID (0 for whole charging point, >=1 for specific connector)
    - **status**: Initial status (default: "Available")
    - **error_code**: Optional error code
    """
    # Verify charger exists
    charger = db.query(Charger).filter(Charger.id == connector.charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail=f"Charger with id '{connector.charger_id}' not found")
    
    # Check if connector already exists for this charger
    existing = db.query(Connector).filter(
        and_(
            Connector.charger_id == connector.charger_id,
            Connector.connector_id == connector.connector_id
        )
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Connector with connector_id {connector.connector_id} already exists for charger {connector.charger_id}"
        )
    
    # Create new connector
    new_connector = Connector(
        charger_id=connector.charger_id,
        connector_id=connector.connector_id,
        status=connector.status or "Available",
        error_code=connector.error_code,
        energy_delivered=0.0,
        power_delivered=0.0
    )
    
    db.add(new_connector)
    db.commit()
    db.refresh(new_connector)
    
    return new_connector

@router.get("/connectors", response_model=List[ConnectorResponse])
async def get_connectors(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    charger_id: Optional[str] = Query(None, description="Filter by charger ID"),
    connector_id: Optional[int] = Query(None, ge=0, description="Filter by OCPP connector ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db)
):
    """
    Get list of connectors with optional filtering
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **charger_id**: Filter by charger ID
    - **connector_id**: Filter by OCPP connector ID
    - **status**: Filter by status (Available, Charging, Faulted, etc.)
    """
    query = db.query(Connector)
    
    # Apply filters
    if charger_id:
        query = query.filter(Connector.charger_id == charger_id)
    if connector_id is not None:
        query = query.filter(Connector.connector_id == connector_id)
    if status:
        query = query.filter(Connector.status == status)
    
    # Apply pagination and ordering
    connectors = query.order_by(desc(Connector.updated_at)).offset(skip).limit(limit).all()
    
    return connectors

@router.get("/connectors/{connector_id}", response_model=ConnectorDetailResponse)
async def get_connector(
    connector_id: int = Path(..., description="Database ID of the connector"),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific connector
    
    - **connector_id**: Database ID of the connector
    """
    connector = db.query(Connector).filter(Connector.id == connector_id).first()
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    # Get charger information
    charger = db.query(Charger).filter(Charger.id == connector.charger_id).first()
    charger_data = None
    if charger:
        charger_data = {
            "id": charger.id,
            "vendor": charger.vendor,
            "model": charger.model,
            "serial_number": charger.serial_number,
            "status": charger.status,
            "is_connected": charger.is_connected
        }
    
    response = ConnectorDetailResponse(
        id=connector.id,
        charger_id=connector.charger_id,
        connector_id=connector.connector_id,
        status=connector.status,
        error_code=connector.error_code,
        energy_delivered=connector.energy_delivered,
        power_delivered=connector.power_delivered,
        created_at=connector.created_at,
        updated_at=connector.updated_at,
        charger=charger_data
    )
    
    return response

@router.get("/chargers/{charger_id}/connectors", response_model=List[ConnectorResponse])
async def get_charger_connectors(
    charger_id: str = Path(..., description="ID of the charger"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db)
):
    """
    Get all connectors for a specific charger
    
    - **charger_id**: ID of the charger
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **status**: Filter by status
    """
    # Verify charger exists
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    query = db.query(Connector).filter(Connector.charger_id == charger_id)
    
    if status:
        query = query.filter(Connector.status == status)
    
    connectors = query.order_by(Connector.connector_id).offset(skip).limit(limit).all()
    
    return connectors

@router.put("/connectors/{connector_id}", response_model=ConnectorResponse)
async def update_connector(
    connector_id: int = Path(..., description="Database ID of the connector"),
    update_data: ConnectorUpdateRequest = ...,
    db: Session = Depends(get_db)
):
    """
    Update connector information
    
    - **connector_id**: Database ID of the connector
    - **status**: New status (optional)
    - **error_code**: New error code (optional)
    - **energy_delivered**: Total energy delivered in kWh (optional)
    - **power_delivered**: Current power delivered in kW (optional)
    """
    connector = db.query(Connector).filter(Connector.id == connector_id).first()
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    # Update fields
    if update_data.status is not None:
        connector.status = update_data.status
    if update_data.error_code is not None:
        connector.error_code = update_data.error_code
    if update_data.energy_delivered is not None:
        connector.energy_delivered = update_data.energy_delivered
    if update_data.power_delivered is not None:
        connector.power_delivered = update_data.power_delivered
    
    connector.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(connector)
    
    return connector

@router.delete("/connectors/{connector_id}", status_code=204)
async def delete_connector(
    connector_id: int = Path(..., description="Database ID of the connector"),
    db: Session = Depends(get_db)
):
    """
    Delete a connector
    
    - **connector_id**: Database ID of the connector
    
    **Note**: This will fail if the connector has active sessions.
    """
    connector = db.query(Connector).filter(Connector.id == connector_id).first()
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    # Check if connector has active sessions
    from app.models.database import Session as DBSession
    active_sessions = db.query(DBSession).filter(
        and_(
            DBSession.connector_id == connector_id,
            DBSession.status == "Active"
        )
    ).count()
    
    if active_sessions > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete connector with {active_sessions} active session(s). Please stop all active sessions first."
        )
    
    db.delete(connector)
    db.commit()
    
    return None

@router.get("/connectors/{connector_id}/statistics")
async def get_connector_statistics(
    connector_id: int = Path(..., description="Database ID of the connector"),
    db: Session = Depends(get_db)
):
    """
    Get statistics for a specific connector
    
    - **connector_id**: Database ID of the connector
    """
    connector = db.query(Connector).filter(Connector.id == connector_id).first()
    
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    
    from app.models.database import Session as DBSession
    from sqlalchemy import func
    
    # Get session statistics
    total_sessions = db.query(DBSession).filter(DBSession.connector_id == connector_id).count()
    active_sessions = db.query(DBSession).filter(
        and_(
            DBSession.connector_id == connector_id,
            DBSession.status == "Active"
        )
    ).count()
    completed_sessions = db.query(DBSession).filter(
        and_(
            DBSession.connector_id == connector_id,
            DBSession.status == "Completed"
        )
    ).count()
    
    # Get total energy delivered from sessions
    total_energy = db.query(func.sum(DBSession.energy_delivered)).filter(
        DBSession.connector_id == connector_id
    ).scalar() or 0.0
    
    # Get total cost from sessions
    total_cost = db.query(func.sum(DBSession.cost)).filter(
        DBSession.connector_id == connector_id
    ).scalar() or 0.0
    
    return {
        "connector_id": connector_id,
        "charger_id": connector.charger_id,
        "ocpp_connector_id": connector.connector_id,
        "status": connector.status,
        "error_code": connector.error_code,
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
        "completed_sessions": completed_sessions,
        "total_energy_delivered_kwh": float(total_energy),
        "total_cost": float(total_cost),
        "current_energy_delivered": connector.energy_delivered,
        "current_power_delivered": connector.power_delivered,
        "created_at": connector.created_at,
        "updated_at": connector.updated_at
    }

