"""
OCPP control endpoints for remote operations
"""
from pydantic import BaseModel, validator, Field
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid
import json
import logging
from typing import Literal
from app.models.database import get_db, ConnectionEvent, Connector,SessionLocal

logger = logging.getLogger(__name__)

from app.core.security import require_permission
from app.models.database import get_db, Charger, Session as DBSession, ConnectionEvent
from app.services.ocpp_handler import OCPPHandler
from app.services.session_manager import SessionManager

router = APIRouter()

# --- New endpoints for start/stop charging ---

import uuid
from fastapi import Request

class StartChargingRequest(BaseModel):
    charger_id: str
    id_tag: str
    connector_id: int = 1

class StopChargingRequest(BaseModel):
    charger_id: str
    transaction_id: int

# Stats response models
class ConnectionStats(BaseModel):
    charger_id: str
    is_connected: bool
    connection_time: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    status: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    firmware_version: Optional[str] = None

class OCPPStats(BaseModel):
    messages_sent: int
    messages_received: int
    messages_failed: int
    connections_total: int
    connections_active: int
    active_connections: int
    master_connections: int
    pending_messages: int
    active_chargers: List[ConnectionStats]

class ConnectionEventResponse(BaseModel):
    id: int
    charger_id: str
    event_type: str
    connection_id: Optional[str] = None
    remote_address: Optional[str] = None
    user_agent: Optional[str] = None
    subprotocol: Optional[str] = None
    reason: Optional[str] = None
    session_duration: Optional[int] = None
    timestamp: str
    event_metadata: Optional[Dict[str, Any]] = None


@router.post("/charging/start", include_in_schema=True)
async def start_charging(request: Request, body: StartChargingRequest):
    """
    Start charging by sending RemoteStartTransaction to the charger via WebSocket.
    """
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler or not hasattr(ocpp_handler, "charger_connections") or body.charger_id not in ocpp_handler.charger_connections:
        raise HTTPException(status_code=404, detail="Charger not connected")

    # Build OCPP RemoteStartTransaction message
    message_id = str(uuid.uuid4())
    ocpp_message = [
        2,  # CALL message type
        message_id,
        "RemoteStartTransaction",
        {
            "connectorId": body.connector_id,
            "idTag": body.id_tag
        }
    ]

    # Send message to charger
    send_func = getattr(ocpp_handler, "send_message_to_charger", None)
    if not send_func:
        raise HTTPException(status_code=500, detail="OCPP handler missing send_message_to_charger")
    success = await send_func(body.charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send start command")

    return {"status": "sent", "message_id": message_id}


@router.post("/charging/stop", include_in_schema=True)
async def stop_charging(request: Request, body: StopChargingRequest):
    """
    Stop charging by sending RemoteStopTransaction to the charger via WebSocket.
    """
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler or not hasattr(ocpp_handler, "charger_connections") or body.charger_id not in ocpp_handler.charger_connections:
        raise HTTPException(status_code=404, detail="Charger not connected")

    # Build OCPP RemoteStopTransaction message
    message_id = str(uuid.uuid4())
    ocpp_message = [
        2,  # CALL message type
        message_id,
        "RemoteStopTransaction",
        {
            "transactionId": body.transaction_id
        }
    ]

    # Send message to charger
    send_func = getattr(ocpp_handler, "send_message_to_charger", None)
    if not send_func:
        raise HTTPException(status_code=500, detail="OCPP handler missing send_message_to_charger")
    success = await send_func(body.charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send stop command")

    return {"status": "sent", "message_id": message_id}

# Pydantic models for requests
class RemoteStartRequest(BaseModel):
    charger_id: str
    id_tag: str
    connector_id: Optional[int] = None
    charging_profile: Optional[Dict[str, Any]] = None

class RemoteStopRequest(BaseModel):
    charger_id: str
    transaction_id: int

class UnlockConnectorRequest(BaseModel):
    charger_id: str
    connector_id: int

class RebootRequest(BaseModel):
    charger_id: str
    type: str = "Soft"  # Soft or Hard

class GetConfigurationRequest(BaseModel):
    charger_id: str
    key: Optional[List[str]] = None

class SetConfigurationRequest(BaseModel):
    charger_id: str
    key: str = Field(..., max_length=50, description="Configuration key (max 50 chars)")
    value: str = Field(..., max_length=500, description="Configuration value (max 500 chars)")

    @validator('key')
    def validate_key(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Key must not be empty')
        return v.strip()

    @validator('value')
    def validate_value(cls, v):
        if len(v.strip()) == 0:
            raise ValueError('Value must not be empty')
        return v.strip()
    
class ClearCacheRequest(BaseModel):
    charger_id: str

class ChangeAvailabilityRequest(BaseModel):
    charger_id: str
    connector_id: int = Field(..., ge=0, description="Connector ID (0 for entire charger)")
    type: Literal["Operative", "Inoperative"] = Field(..., description="Availability type")

    @validator('connector_id')
    def validate_connector_id(cls, v, values):
        if v == 0:
            return v  # Charger-level availability is valid
        db = SessionLocal()
        try:
            charger_id = values.get('charger_id')
            if not charger_id:
                raise ValueError("Charger ID must be provided")
            connector = db.query(Connector).filter(
                Connector.charger_id == charger_id,
                Connector.connector_id == v
            ).first()
            if not connector:
                raise ValueError(f"Connector {v} does not exist for charger {charger_id}")
            return v
        finally:
            db.close()

class ResetRequest(BaseModel):
    charger_id: str
    type: str = "Soft"  # Soft or Hard

class TriggerMessageRequest(BaseModel):
    charger_id: str
    requested_message: str
    connector_id: Optional[int] = None

# Response models
class OCPPResponse(BaseModel):
    status: str
    message_id: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

@router.post("/ocpp/remote/start", response_model=OCPPResponse)
async def remote_start_transaction(
    request: Request,
    remote_start_req: RemoteStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Start a charging session remotely"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    charger_id = remote_start_req.charger_id

    # --- Fix: Check for empty charger_id and return a clear error ---
    if not charger_id or charger_id.strip() == "":
        raise HTTPException(
            status_code=400,
            detail="Invalid charger_id. Please provide a non-empty charger_id and ensure your OCPP client connects to /ocpp/{charger_id}."
        )

    # Check if charger exists in DB
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    # If not in DB, check if it's connected in ocpp_handler
    if not charger:
        if (
            ocpp_handler
            and hasattr(ocpp_handler, "charger_connections")
            and charger_id in ocpp_handler.charger_connections
        ):
            charger = Charger(id=charger_id, is_connected=True, status="Available")
            db.add(charger)
            db.commit()
            db.refresh(charger)
        else:
            # --- Add diagnostic: List connected charger IDs for debugging ---
            connected_ids = []
            if ocpp_handler and hasattr(ocpp_handler, "charger_connections"):
                connected_ids = list(ocpp_handler.charger_connections.keys())
            raise HTTPException(
                status_code=404,
                detail=f"Charger not found. Please ensure the charger is connected at least once via OCPP WebSocket. Connected charger_ids: {connected_ids}"
            )

    if not charger.is_connected:
        if (
            ocpp_handler
            and hasattr(ocpp_handler, "charger_connections")
            and charger_id in ocpp_handler.charger_connections
        ):
            charger.is_connected = True
            charger.status = "Available"
            db.commit()
        else:
            raise HTTPException(status_code=400, detail="Charger is not connected")

    # Generate unique message ID
    message_id = str(uuid.uuid4())

    # TODO: Send RemoteStartTransaction via WebSocket
    # This would require access to the OCPP handler
    # For now, return a mock response

    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message="Remote start command sent successfully"
    )

@router.post("/ocpp/remote/stop", response_model=OCPPResponse)
async def remote_stop_transaction(
    request: RemoteStopRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Stop a running charging session"""
    
    # Verify charger exists and is connected
    charger = db.query(Charger).filter(Charger.id == request.charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    if not charger.is_connected:
        raise HTTPException(status_code=400, detail="Charger is not connected")
    
    # Verify session exists
    session = db.query(DBSession).filter(
        DBSession.charger_id == request.charger_id,
        DBSession.transaction_id == request.transaction_id,
        DBSession.status == "Active"
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Active session not found")
    
    # Generate unique message ID
    message_id = str(uuid.uuid4())
    
    # TODO: Send RemoteStopTransaction via WebSocket
    
    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message="Remote stop command sent successfully"
    )

@router.post("/ocpp/unlock", response_model=OCPPResponse)
async def unlock_connector(
    request: UnlockConnectorRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Unlock a connector manually"""
    
    # Verify charger exists and is connected
    charger = db.query(Charger).filter(Charger.id == request.charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    if not charger.is_connected:
        raise HTTPException(status_code=400, detail="Charger is not connected")
    
    # Generate unique message ID
    message_id = str(uuid.uuid4())
    
    # TODO: Send UnlockConnector via WebSocket
    
    return OCPPResponse(
        status="Unlocked",
        message_id=message_id,
        message="Unlock command sent successfully"
    )

@router.post("/ocpp/reboot", response_model=OCPPResponse)
async def reboot_charger(
    request: RebootRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Send reboot command to a charger"""
    
    # Verify charger exists and is connected
    charger = db.query(Charger).filter(Charger.id == request.charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    if not charger.is_connected:
        raise HTTPException(status_code=400, detail="Charger is not connected")
    
    # Validate reboot type
    if request.type not in ["Soft", "Hard"]:
        raise HTTPException(status_code=400, detail="Invalid reboot type. Must be 'Soft' or 'Hard'")
    
    # Generate unique message ID
    message_id = str(uuid.uuid4())
    
    # TODO: Send Reset via WebSocket
    
    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message=f"Reboot command ({request.type}) sent successfully"
    )

@router.post("/ocpp/configuration/get", response_model=OCPPResponse)
async def get_configuration(
    request: GetConfigurationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Retrieve charger configuration parameters"""
    
    # Verify charger exists and is connected
    charger = db.query(Charger).filter(Charger.id == request.charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    if not charger.is_connected:
        raise HTTPException(status_code=400, detail="Charger is not connected")
    
    # Generate unique message ID
    message_id = str(uuid.uuid4())
    
    # TODO: Send GetConfiguration via WebSocket
    # For now, return stored configuration
    configuration = charger.configuration or {}
    
    if request.key:
        # Filter by requested keys
        filtered_config = {k: v for k, v in configuration.items() if k in request.key}
        configuration = filtered_config
    
    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message="Configuration retrieved successfully",
        data={"configuration": configuration}
    )

from fastapi import Request  # Add if not present

@router.post("/ocpp/configuration/set", response_model=OCPPResponse)
async def set_configuration(
    request: Request,
    set_config: SetConfigurationRequest,  # Uses NEW model
    db: Session = Depends(get_db)
):
    """Update configuration parameters on a charger (OCPP ChangeConfiguration)"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")

    charger_id = set_config.charger_id

    # Robust connection check (from /charging/remote_start)
    latest_connection_event = db.query(ConnectionEvent).filter(
        ConnectionEvent.charger_id == charger_id
    ).order_by(ConnectionEvent.timestamp.desc()).first()

    if not latest_connection_event:
        raise HTTPException(
            status_code=404,
            detail=f"Charger '{charger_id}' has never connected."
        )

    if latest_connection_event.event_type != "CONNECT":
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{charger_id}' is not currently connected. Last event: '{latest_connection_event.event_type}'"
        )

    connected_ids = list(ocpp_handler.charger_connections.keys())
    if charger_id not in connected_ids:
        disconnect_event = ConnectionEvent(
            charger_id=charger_id,
            event_type="DISCONNECT",
            connection_id=latest_connection_event.connection_id,
            reason="Connection lost during command",
            session_duration=int((datetime.utcnow() - latest_connection_event.timestamp).total_seconds())
        )
        db.add(disconnect_event)
        db.commit()
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{charger_id}' connection lost."
        )

    # Construct OCPP message
    message_id = str(uuid.uuid4())
    ocpp_payload = {"key": set_config.key, "value": set_config.value}
    ocpp_message = [2, message_id, "ChangeConfiguration", ocpp_payload]

    # Send via OCPPHandler (automatically adds to pending_messages)
    success = await ocpp_handler.send_message_to_charger(charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send ChangeConfiguration command")

    # Log outgoing request immediately
    await ocpp_handler.log_message(
        charger_id, "OUT", "ChangeConfiguration", message_id, "Pending",
        None, json.dumps(ocpp_message), None
    )

    logger.info(f"ChangeConfiguration sent to {charger_id}: key='{set_config.key}', value='{set_config.value}' (message_id={message_id})")

    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message=f"ChangeConfiguration command sent for key '{set_config.key}'"
    )

@router.post("/ocpp/availability/change", response_model=OCPPResponse)
async def change_availability(
    request: ChangeAvailabilityRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Change availability of a connector"""
    
    # Verify charger exists and is connected
    charger = db.query(Charger).filter(Charger.id == request.charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    if not charger.is_connected:
        raise HTTPException(status_code=400, detail="Charger is not connected")
    
    # Validate availability type
    if request.type not in ["Inoperative", "Operative"]:
        raise HTTPException(status_code=400, detail="Invalid availability type. Must be 'Inoperative' or 'Operative'")
    
    # Generate unique message ID
    message_id = str(uuid.uuid4())
    
    # TODO: Send ChangeAvailability via WebSocket
    
    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message=f"Availability change command sent successfully"
    )


@router.post("/ocpp/availability/change", response_model=OCPPResponse)
async def change_availability(
    request: Request,
    change_availability: ChangeAvailabilityRequest,
    db: Session = Depends(get_db)
):
    """Change the availability of a charger or connector (OCPP ChangeAvailability)"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")

    charger_id = change_availability.charger_id
    connector_id = change_availability.connector_id
    availability_type = change_availability.type

    # Robust connection check
    latest_connection_event = db.query(ConnectionEvent).filter(
        ConnectionEvent.charger_id == charger_id
    ).order_by(ConnectionEvent.timestamp.desc()).first()

    if not latest_connection_event:
        raise HTTPException(
            status_code=404,
            detail=f"Charger '{charger_id}' has never connected."
        )

    if latest_connection_event.event_type != "CONNECT":
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{charger_id}' is not currently connected. Last event: '{latest_connection_event.event_type}'"
        )

    connected_ids = list(ocpp_handler.charger_connections.keys())
    if charger_id not in connected_ids:
        disconnect_event = ConnectionEvent(
            charger_id=charger_id,
            event_type="DISCONNECT",
            connection_id=latest_connection_event.connection_id,
            reason="Connection lost during command",
            session_duration=int((datetime.utcnow() - latest_connection_event.timestamp).total_seconds())
        )
        db.add(disconnect_event)
        db.commit()
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{charger_id}' connection lost."
        )

    # Construct OCPP message
    message_id = str(uuid.uuid4())
    ocpp_payload = {"connectorId": connector_id, "type": availability_type}
    ocpp_message = [2, message_id, "ChangeAvailability", ocpp_payload]

    # Send via OCPPHandler (automatically adds to pending_messages)
    success = await ocpp_handler.send_message_to_charger(charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send ChangeAvailability command")

    # Log outgoing request immediately
    await ocpp_handler.log_message(
        charger_id, "OUT", "ChangeAvailability", message_id, "Pending",
        None, json.dumps(ocpp_message), None
    )

    logger.info(f"ChangeAvailability sent to {charger_id}: connectorId={connector_id}, type={availability_type} (message_id={message_id})")

    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message=f"ChangeAvailability command sent for connector {connector_id} to {availability_type}"
    )

@router.post("/ocpp/reset", response_model=OCPPResponse)
async def reset_charger(
    request: ResetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Send reset command to a charger"""
    
    # Verify charger exists and is connected
    charger = db.query(Charger).filter(Charger.id == request.charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    if not charger.is_connected:
        raise HTTPException(status_code=400, detail="Charger is not connected")
    
    # Validate reset type
    if request.type not in ["Soft", "Hard"]:
        raise HTTPException(status_code=400, detail="Invalid reset type. Must be 'Soft' or 'Hard'")
    
    # Generate unique message ID
    message_id = str(uuid.uuid4())
    
    # TODO: Send Reset via WebSocket
    
    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message=f"Reset command ({request.type}) sent successfully"
    )

@router.post("/ocpp/trigger", response_model=OCPPResponse)
async def trigger_message(
    request: TriggerMessageRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Trigger a specific message from a charger"""
    
    # Verify charger exists and is connected
    charger = db.query(Charger).filter(Charger.id == request.charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    if not charger.is_connected:
        raise HTTPException(status_code=400, detail="Charger is not connected")
    
    # Validate requested message
    valid_messages = [
        "BootNotification", "DiagnosticsStatusNotification", "FirmwareStatusNotification",
        "Heartbeat", "MeterValues", "StatusNotification"
    ]
    
    if request.requested_message not in valid_messages:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid requested message. Must be one of: {', '.join(valid_messages)}"
        )
    
    # Generate unique message ID
    message_id = str(uuid.uuid4())
    
    # TODO: Send TriggerMessage via WebSocket
    
    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message=f"Trigger message command sent successfully"
    )

@router.get("/ocpp/commands/pending")
async def get_pending_commands(
    charger_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get pending OCPP commands (for debugging)"""
    
    # TODO: Implement command queue tracking
    # This would require a command queue system
    
    return {
        "message": "Pending commands endpoint not yet implemented",
        "charger_id": charger_id,
        "pending_commands": []
    }

class RemoteStartBody(BaseModel):
    charger_id: str
    id_tag: str
    connector_id: int = 1

class RemoteStopBody(BaseModel):
    charger_id: str
    transaction_id: int

@router.post("/charging/remote_start")
async def charging_remote_start(request: Request, body: RemoteStartBody, db: Session = Depends(get_db)):
    """
    Remotely start charging by sending RemoteStartTransaction to the charger via WebSocket.
    Checks database for most recent connection event to verify charger is still connected.
    """
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler or not hasattr(ocpp_handler, "charger_connections"):
        raise HTTPException(status_code=500, detail="OCPP handler not available")
    
    # Check database for most recent connection event for this charger
    latest_connection_event = db.query(ConnectionEvent).filter(
        ConnectionEvent.charger_id == body.charger_id
    ).order_by(ConnectionEvent.timestamp.desc()).first()
    
    if not latest_connection_event:
        raise HTTPException(
            status_code=404,
            detail=f"Charger '{body.charger_id}' has never connected. Please ensure the charger connects via OCPP WebSocket first."
        )
    
    # Check if the most recent event is a CONNECT event (charger is still connected)
    if latest_connection_event.event_type != "CONNECT":
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{body.charger_id}' is not currently connected. Last event was '{latest_connection_event.event_type}' at {latest_connection_event.timestamp}"
        )
    
    # Double-check that charger is still in active connections
    connected_ids = list(ocpp_handler.charger_connections.keys())
    if body.charger_id not in connected_ids:
        # Update the connection event to DISCONNECT if it's not in active connections
        disconnect_event = ConnectionEvent(
            charger_id=body.charger_id,
            event_type="DISCONNECT",
            connection_id=latest_connection_event.connection_id,
            reason="Connection lost - not in active connections",
            session_duration=int((datetime.utcnow() - latest_connection_event.timestamp).total_seconds())
        )
        db.add(disconnect_event)
        db.commit()
        
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{body.charger_id}' connection was lost. Please reconnect the charger via OCPP WebSocket."
        )
    
    # Verify the connection_id matches (extra safety check)
    if latest_connection_event.connection_id != ocpp_handler.connection_ids.get(body.charger_id):
        logger.warning(f"Connection ID mismatch for charger {body.charger_id}. DB: {latest_connection_event.connection_id}, Active: {ocpp_handler.connection_ids.get(body.charger_id)}")
    
    # All checks passed - send remote start command
    message_id = str(uuid.uuid4())
    ocpp_message = [
        2,  # CALL
        message_id,
        "RemoteStartTransaction",
        {
            "connectorId": body.connector_id,
            "idTag": body.id_tag
        }
    ]
    
    send_func = getattr(ocpp_handler, "send_message_to_charger", None)
    if not send_func:
        raise HTTPException(status_code=500, detail="OCPP handler missing send_message_to_charger")
    
    success = await send_func(body.charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send RemoteStartTransaction")
    
    # Log the remote start command
    logger.info(f"Remote start command sent to charger {body.charger_id} with connection_id {latest_connection_event.connection_id}")
    
    return {
        "status": "sent", 
        "message_id": message_id,
        "charger_id": body.charger_id,
        "connection_id": latest_connection_event.connection_id,
        "last_connection_time": latest_connection_event.timestamp.isoformat()
    }

@router.post("/charging/remote_stop")
async def charging_remote_stop(request: Request, body: RemoteStopBody, db: Session = Depends(get_db)):
    """
    Remotely stop charging by sending RemoteStopTransaction to the charger via WebSocket.
    """
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler or not hasattr(ocpp_handler, "charger_connections"):
        raise HTTPException(status_code=500, detail="OCPP handler not available")
    connected_ids = list(ocpp_handler.charger_connections.keys())
    if not connected_ids:
        raise HTTPException(
            status_code=404,
            detail="No chargers are currently connected via WebSocket. Please ensure your OCPP client is connected to wss://localhost:9001/ocpp/{charger_id} before sending remote commands."
        )
    if body.charger_id not in connected_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Charger '{body.charger_id}' not connected. Connected charger_ids: {connected_ids}. Please connect your OCPP client to wss://localhost:9001/ocpp/{body.charger_id}"
        )

    message_id = str(uuid.uuid4())
    ocpp_message = [
        2,  # CALL
        message_id,
        "RemoteStopTransaction",
        {
            "transactionId": body.transaction_id
        }
    ]
    send_func = getattr(ocpp_handler, "send_message_to_charger", None)
    if not send_func:
        raise HTTPException(status_code=500, detail="OCPP handler missing send_message_to_charger")
    success = await send_func(body.charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send RemoteStopTransaction")
    return {"status": "sent", "message_id": message_id}


@router.post("/ocpp/cache/clear", response_model=OCPPResponse)
async def clear_cache(
    request: Request,
    clear_cache: ClearCacheRequest,
    db: Session = Depends(get_db)
):
    """Clear the authorization cache on a charger (OCPP ClearCache)"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")

    charger_id = clear_cache.charger_id

    # Robust connection check (from /charging/remote_start)
    latest_connection_event = db.query(ConnectionEvent).filter(
        ConnectionEvent.charger_id == charger_id
    ).order_by(ConnectionEvent.timestamp.desc()).first()

    if not latest_connection_event:
        raise HTTPException(
            status_code=404,
            detail=f"Charger '{charger_id}' has never connected."
        )

    if latest_connection_event.event_type != "CONNECT":
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{charger_id}' is not currently connected. Last event: '{latest_connection_event.event_type}'"
        )

    connected_ids = list(ocpp_handler.charger_connections.keys())
    if charger_id not in connected_ids:
        disconnect_event = ConnectionEvent(
            charger_id=charger_id,
            event_type="DISCONNECT",
            connection_id=latest_connection_event.connection_id,
            reason="Connection lost during command",
            session_duration=int((datetime.utcnow() - latest_connection_event.timestamp).total_seconds())
        )
        db.add(disconnect_event)
        db.commit()
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{charger_id}' connection lost."
        )

    # Construct OCPP message
    message_id = str(uuid.uuid4())
    ocpp_payload = {}
    ocpp_message = [2, message_id, "ClearCache", ocpp_payload]

    # Send via OCPPHandler (automatically adds to pending_messages)
    success = await ocpp_handler.send_message_to_charger(charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send ClearCache command")

    # Log outgoing request immediately
    await ocpp_handler.log_message(
        charger_id, "OUT", "ClearCache", message_id, "Pending",
        None, json.dumps(ocpp_message), None
    )

    logger.info(f"ClearCache sent to {charger_id} (message_id={message_id})")

    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message="ClearCache command sent"
    )
# --- Stats and monitoring endpoints ---

@router.get("/stats", response_model=OCPPStats, include_in_schema=True)
async def get_ocpp_stats(request: Request, db: Session = Depends(get_db)):
    """
    Get comprehensive OCPP handler statistics including all active connections.
    """
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")
    
    # Get basic stats from handler
    basic_stats = ocpp_handler.get_stats()
    
    # Get detailed charger information from database
    active_chargers = []
    for charger_id in ocpp_handler.charger_connections.keys():
        charger = db.query(Charger).filter(Charger.id == charger_id).first()
        if charger:
            active_chargers.append(ConnectionStats(
                charger_id=charger.id,
                is_connected=charger.is_connected,
                connection_time=charger.connection_time,
                last_heartbeat=charger.last_heartbeat,
                status=charger.status,
                vendor=charger.vendor,
                model=charger.model,
                firmware_version=charger.firmware_version
            ))
        else:
            # Charger is connected but not in database
            active_chargers.append(ConnectionStats(
                charger_id=charger_id,
                is_connected=True,
                status="Connected"
            ))
    
    return OCPPStats(
        messages_sent=basic_stats.get("messages_sent", 0),
        messages_received=basic_stats.get("messages_received", 0),
        messages_failed=basic_stats.get("messages_failed", 0),
        connections_total=basic_stats.get("connections_total", 0),
        connections_active=basic_stats.get("connections_active", 0),
        active_connections=basic_stats.get("active_connections", 0),
        master_connections=basic_stats.get("master_connections", 0),
        pending_messages=basic_stats.get("pending_messages", 0),
        active_chargers=active_chargers
    )


@router.get("/connections", response_model=List[ConnectionStats], include_in_schema=True)
async def get_active_connections(request: Request, db: Session = Depends(get_db)):
    """
    Get detailed information about all active charger connections.
    """
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")
    
    active_connections = []
    for charger_id in ocpp_handler.charger_connections.keys():
        charger = db.query(Charger).filter(Charger.id == charger_id).first()
        if charger:
            active_connections.append(ConnectionStats(
                charger_id=charger.id,
                is_connected=charger.is_connected,
                connection_time=charger.connection_time,
                last_heartbeat=charger.last_heartbeat,
                status=charger.status,
                vendor=charger.vendor,
                model=charger.model,
                firmware_version=charger.firmware_version
            ))
        else:
            # Charger is connected but not in database
            active_connections.append(ConnectionStats(
                charger_id=charger_id,
                is_connected=True,
                status="Connected"
            ))
    
    return active_connections


@router.get("/connections/{charger_id}", response_model=ConnectionStats, include_in_schema=True)
async def get_charger_connection(charger_id: str, request: Request, db: Session = Depends(get_db)):
    """
    Get detailed information about a specific charger connection.
    """
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")
    
    # Check if charger is connected
    if charger_id not in ocpp_handler.charger_connections:
        raise HTTPException(status_code=404, detail=f"Charger {charger_id} not connected")
    
    # Get charger information from database
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if charger:
        return ConnectionStats(
            charger_id=charger.id,
            is_connected=charger.is_connected,
            connection_time=charger.connection_time,
            last_heartbeat=charger.last_heartbeat,
            status=charger.status,
            vendor=charger.vendor,
            model=charger.model,
            firmware_version=charger.firmware_version
        )
    else:
        # Charger is connected but not in database
        return ConnectionStats(
            charger_id=charger_id,
            is_connected=True,
            status="Connected"
        )


@router.get("/stats/summary", include_in_schema=True)
async def get_stats_summary(request: Request):
    """
    Get a quick summary of OCPP handler statistics.
    """
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")
    
    stats = ocpp_handler.get_stats()
    return {
        "total_connections": stats.get("connections_total", 0),
        "active_connections": stats.get("active_connections", 0),
        "master_connections": stats.get("master_connections", 0),
        "messages_sent": stats.get("messages_sent", 0),
        "messages_received": stats.get("messages_received", 0),
        "messages_failed": stats.get("messages_failed", 0),
        "pending_messages": stats.get("pending_messages", 0),
        "connected_charger_ids": list(ocpp_handler.charger_connections.keys())
    }


# --- Connection Events endpoints ---

@router.get("/connection-events", response_model=List[ConnectionEventResponse], include_in_schema=True)
async def get_connection_events(
    charger_id: Optional[str] = None, 
    limit: int = 100, 
    request: Request = None, 
    db: Session = Depends(get_db)
):
    """
    Get WebSocket connection events from database.
    """
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")
    
    # Get events from OCPP handler
    events = ocpp_handler.get_connection_events(charger_id=charger_id, limit=limit)
    
    return [ConnectionEventResponse(**event) for event in events]


@router.get("/connection-events/{charger_id}", response_model=List[ConnectionEventResponse], include_in_schema=True)
async def get_charger_connection_events(
    charger_id: str, 
    limit: int = 100, 
    request: Request = None, 
    db: Session = Depends(get_db)
):
    """
    Get connection events for a specific charger.
    """
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")
    
    # Get events for specific charger
    events = ocpp_handler.get_connection_events(charger_id=charger_id, limit=limit)
    
    return [ConnectionEventResponse(**event) for event in events]


@router.get("/connection-events/stats", include_in_schema=True)
async def get_connection_event_stats(request: Request = None, db: Session = Depends(get_db)):
    """
    Get statistics about connection events.
    """
    try:
        # Get total connection events count
        total_events = db.query(ConnectionEvent).count()
        
        # Get events by type
        connect_events = db.query(ConnectionEvent).filter(ConnectionEvent.event_type == "CONNECT").count()
        disconnect_events = db.query(ConnectionEvent).filter(ConnectionEvent.event_type == "DISCONNECT").count()
        
        # Get events by charger
        charger_events = db.query(ConnectionEvent.charger_id, db.func.count(ConnectionEvent.id)).group_by(ConnectionEvent.charger_id).all()
        
        # Get recent events (last 24 hours)
        from datetime import datetime, timedelta
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_events = db.query(ConnectionEvent).filter(ConnectionEvent.timestamp >= yesterday).count()
        
        return {
            "total_events": total_events,
            "connect_events": connect_events,
            "disconnect_events": disconnect_events,
            "recent_events_24h": recent_events,
            "events_by_charger": [{"charger_id": charger_id, "event_count": count} for charger_id, count in charger_events]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get connection event stats: {e}")

# Make sure your router is included with the correct prefix in app.main.py:
# app.include_router(ocpp_control.router, prefix="/api", tags=["OCPP Control"])

# Also, ensure your endpoint is defined as:
# @router.post("/ocpp/remote/start", response_model=OCPPResponse)

# If you still get 404, check that:
# - The file is named ocpp_control.py and is imported in app.main.py
# - The router is included with prefix="/api"
# - You are POSTing to http://localhost:8001/api/ocpp/remote/start

# No code changes needed if all above is correct.
# No code changes needed if all above is correct.
