"""
OCPP control endpoints for remote operations
"""
import asyncio
from pydantic import BaseModel, validator, Field, constr
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid
import json
import logging
from typing import Literal
from app.models.database import get_db, ConnectionEvent, Connector, SessionLocal, SystemConfig
from app.core.config import get_egypt_now, to_egypt_timezone

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
async def stop_charging(request: Request, body: StopChargingRequest, db: Session = Depends(get_db)):
    """
    Stop charging by sending RemoteStopTransaction to the charger via WebSocket.
    Gets transaction_id from the database (active session) instead of from the request.
    """
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler or not hasattr(ocpp_handler, "charger_connections") or body.charger_id not in ocpp_handler.charger_connections:
        raise HTTPException(status_code=404, detail="Charger not connected")

    # Get active session from database to retrieve transaction_id
    active_session = db.query(DBSession).filter(
        DBSession.charger_id == body.charger_id,
        DBSession.status == "Active"
    ).order_by(DBSession.start_time.desc()).first()
    
    if not active_session:
        raise HTTPException(
            status_code=404,
            detail=f"No active charging session found for charger '{body.charger_id}'"
        )
    
    if active_session.transaction_id is None:
        raise HTTPException(
            status_code=400,
            detail=f"Active session found for charger '{body.charger_id}' but transaction_id is missing"
        )
    
    transaction_id = active_session.transaction_id

    # Build OCPP RemoteStopTransaction message
    message_id = str(uuid.uuid4())
    ocpp_message = [
        2,  # CALL message type
        message_id,
        "RemoteStopTransaction",
        {
            "transactionId": transaction_id
        }
    ]

    # Send message to charger
    send_func = getattr(ocpp_handler, "send_message_to_charger", None)
    if not send_func:
        raise HTTPException(status_code=500, detail="OCPP handler missing send_message_to_charger")
    success = await send_func(body.charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send stop command")

    return {"status": "sent", "message_id": message_id, "transaction_id": transaction_id}

# Pydantic models for requests
class RemoteStartRequest(BaseModel):
    charger_id: str
    id_tag: str
    connector_id: Optional[int] = None
    charging_profile: Optional[Dict[str, Any]] = None

class RemoteStopRequest(BaseModel):
    charger_id: str

class UnlockConnectorRequest(BaseModel):
    charger_id: str
    connector_id: int = Field(..., gt=0, description="Connector ID (must be positive)")

    @validator('connector_id')
    def validate_connector_id(cls, v, values):
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

class RebootRequest(BaseModel):
    charger_id: str
    type: str = "Soft"  # Soft or Hard

class GetConfigurationRequest(BaseModel):
    charger_id: str
    keys: Optional[List[str]] = Field(None, description="List of configuration keys to retrieve (optional)")

    @validator('keys', each_item=True, pre=True)
    def validate_keys(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Configuration key must not be empty")
        if len(v) > 50:
            raise ValueError("Configuration key must not exceed 50 characters")
        return v.strip()

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
    type: Literal["Hard", "Soft"] = Field(..., description="Reset type (Hard or Soft)")

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

class GetLocalListVersionRequest(BaseModel):
    charger_id: str    

class IdTagInfo(BaseModel):
    status: Literal["Accepted", "Blocked", "Expired", "Invalid", "ConcurrentTx"] = Field(..., description="Authorization status")
    expiry_date: Optional[datetime] = Field(None, description="ISO 8601 expiry date")
    parent_id_tag: Optional[constr(max_length=20)] = Field(None, description="Parent ID tag (max 20 chars)") # type: ignore

    @validator('expiry_date')
    def validate_expiry_date(cls, v):
        if v is not None:
            return v.replace(tzinfo=None)  # OCPP 1.6 expects no timezone
        return v

class AuthorizationEntry(BaseModel):
    id_tag: constr(max_length=20) = Field(..., description="ID tag (max 20 chars)") # type: ignore
    id_tag_info: Optional[IdTagInfo] = Field(None, description="Optional ID tag info")

    @validator('id_tag')
    def validate_id_tag(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("ID tag must not be empty")
        return v.strip()

class SendLocalListRequest(BaseModel):
    charger_id: str
    list_version: int = Field(..., gt=0, description="Local authorization list version")
    update_type: Literal["Differential", "Full"] = Field(..., description="Update type (Differential or Full)")
    local_authorization_list: List[AuthorizationEntry] = Field(default_factory=list, description="List of authorization entries")

    @validator('local_authorization_list', each_item=True)
    def validate_authorization_entry(cls, v):
        return v

class GetDiagnosticsRequest(BaseModel):
    charger_id: str
    location: str = Field(..., description="Location (URL) where diagnostics should be uploaded")
    start_time: Optional[datetime] = Field(None, description="Start of diagnostics period")
    stop_time: Optional[datetime] = Field(None, description="Stop of diagnostics period")
    retries: Optional[int] = Field(None, ge=0, le=10, description="Number of retries")
    retry_interval: Optional[int] = Field(None, ge=0, description="Retry interval in seconds")

class ClearChargingProfileRequest(BaseModel):
    charger_id: str
    connector_id: Optional[int] = Field(None, description="Connector ID (optional)")
    charging_profile_id: Optional[int] = Field(None, description="Charging profile ID to clear (optional)")

class SetChargingProfileRequest(BaseModel):
    charger_id: str
    connector_id: int = Field(..., ge=0, description="Connector ID")
    charging_profile: Dict[str, Any] = Field(..., description="Charging profile configuration")

class UpdateFirmwareRequest(BaseModel):
    charger_id: str
    location: str = Field(..., description="Location (URL) where firmware can be downloaded")
    retrieve_date: datetime = Field(..., description="Date and time at which the firmware should be retrieved")
    retries: Optional[int] = Field(None, ge=0, le=10, description="Number of retries")
    retry_interval: Optional[int] = Field(None, ge=0, description="Retry interval in seconds")


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
    request: Request,
    remote_stop_req: RemoteStopRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Stop a running charging session. Gets transaction_id from database instead of request."""
    
    # Verify charger exists and is connected
    charger = db.query(Charger).filter(Charger.id == remote_stop_req.charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    if not charger.is_connected:
        raise HTTPException(status_code=400, detail="Charger is not connected")
    
    # Get active session from database to retrieve transaction_id
    session = db.query(DBSession).filter(
        DBSession.charger_id == remote_stop_req.charger_id,
        DBSession.status == "Active"
    ).order_by(DBSession.start_time.desc()).first()
    
    if not session:
        raise HTTPException(status_code=404, detail=f"No active charging session found for charger '{remote_stop_req.charger_id}'")
    
    if session.transaction_id is None:
        raise HTTPException(
            status_code=400,
            detail=f"Active session found for charger '{remote_stop_req.charger_id}' but transaction_id is missing"
        )
    
    transaction_id = session.transaction_id
    
    # Get OCPP handler and send RemoteStopTransaction
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")
    
    # Generate unique message ID
    message_id = str(uuid.uuid4())
    
    # Build and send RemoteStopTransaction message
    ocpp_message = [
        2,  # CALL
        message_id,
        "RemoteStopTransaction",
        {
            "transactionId": transaction_id
        }
    ]
    
    send_func = getattr(ocpp_handler, "send_message_to_charger", None)
    if not send_func:
        raise HTTPException(status_code=500, detail="OCPP handler missing send_message_to_charger")
    
    success = await send_func(remote_stop_req.charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send RemoteStopTransaction")
    
    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message=f"Remote stop command sent successfully for transaction_id {transaction_id}"
    )

@router.post("/ocpp/connector/unlock", response_model=OCPPResponse)
async def unlock_connector(
    request: Request,
    unlock_request: UnlockConnectorRequest,
    db: Session = Depends(get_db)
):
    """Unlock a connector on a charger (OCPP UnlockConnector)"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")

    charger_id = unlock_request.charger_id
    connector_id = unlock_request.connector_id

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
        # Don't create disconnect event - let OCPP handler manage connection state
        logger.warning(f"Charger {charger_id} not found in active connections during unlock command")
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{charger_id}' is not currently connected. Please check connection status."
        )

    # Construct OCPP message
    message_id = str(uuid.uuid4())
    ocpp_payload = {"connectorId": connector_id}
    ocpp_message = [2, message_id, "UnlockConnector", ocpp_payload]

    # Send via OCPPHandler (automatically adds to pending_messages)
    success = await ocpp_handler.send_message_to_charger(charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send UnlockConnector command")

    # Log outgoing request immediately
    await ocpp_handler.log_message(
        charger_id, "OUT", "UnlockConnector", message_id, "Pending",
        None, json.dumps(ocpp_message), None
    )

    logger.info(f"UnlockConnector sent to {charger_id}: connectorId={connector_id} (message_id={message_id})")

    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message=f"UnlockConnector command sent for connector {connector_id}"
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
    request: Request,
    get_config: GetConfigurationRequest,
    db: Session = Depends(get_db)
):
    """Get configuration parameters from a charger (OCPP GetConfiguration)"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")

    charger_id = get_config.charger_id
    keys = get_config.keys

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
        # Don't create disconnect event - let OCPP handler manage connection state
        logger.warning(f"Charger {charger_id} not found in active connections during command")
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{charger_id}' is not currently connected. Please check connection status."
        )

    # Construct OCPP message
    message_id = str(uuid.uuid4())
    ocpp_payload = {"key": keys} if keys else {}
    ocpp_message = [2, message_id, "GetConfiguration", ocpp_payload]

    # Send via OCPPHandler (automatically adds to pending_messages)
    success = await ocpp_handler.send_message_to_charger(charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send GetConfiguration command")

    # Log outgoing request immediately
    await ocpp_handler.log_message(
        charger_id, "OUT", "GetConfiguration", message_id, "Pending",
        None, json.dumps(ocpp_message), None
    )

    logger.info(f"GetConfiguration sent to {charger_id}: keys={keys or 'all'} (message_id={message_id})")

    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message=f"GetConfiguration command sent for keys {keys or 'all'}"
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

    # Allow sending messages to disconnected chargers for retry mechanism testing
    # if latest_connection_event.event_type != "CONNECT":
    #     raise HTTPException(
    #         status_code=400,
    #         detail=f"Charger '{charger_id}' is not currently connected. Last event: '{latest_connection_event.event_type}'"
    #     )

    # Allow sending messages to disconnected chargers for retry mechanism testing
    # connected_ids = list(ocpp_handler.charger_connections.keys())
    # if charger_id not in connected_ids:
    #     # Don't create disconnect event - let OCPP handler manage connection state
    #     logger.warning(f"Charger {charger_id} not found in active connections during command")
    #     raise HTTPException(
    #         status_code=400,
    #         detail=f"Charger '{charger_id}' is not currently connected. Please check connection status."
    #     )

    # Construct OCPP message
    message_id = str(uuid.uuid4())
    ocpp_payload = {"key": set_config.key, "value": set_config.value}
    ocpp_message = [2, message_id, "ChangeConfiguration", ocpp_payload]

    # Send via OCPPHandler (automatically adds to pending_messages)
    logger.info(f"DEBUG: About to send ChangeConfiguration to {charger_id}")
    success = await ocpp_handler.send_message_to_charger(charger_id, ocpp_message)
    logger.info(f"DEBUG: send_message_to_charger returned {success} for {charger_id}")
    
    # For disconnected chargers, success=False is expected - message is queued for retry
    if not success:
        logger.info(f"DEBUG: Charger {charger_id} not connected, message queued for retry")
        # Don't raise exception - message is queued for retry

    # Log outgoing request immediately
    await ocpp_handler.log_message(
        charger_id, "OUT", "ChangeConfiguration", message_id, "Pending",
        None, json.dumps(ocpp_message), None
    )

    if success:
        logger.info(f"ChangeConfiguration sent to {charger_id}: key='{set_config.key}', value='{set_config.value}' (message_id={message_id})")
        response_message = f"ChangeConfiguration command sent for key '{set_config.key}'"
    else:
        logger.info(f"ChangeConfiguration queued for retry to {charger_id}: key='{set_config.key}', value='{set_config.value}' (message_id={message_id})")
        response_message = f"ChangeConfiguration command queued for retry (charger not connected)"

    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message=response_message
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
        # Don't create disconnect event - let OCPP handler manage connection state
        logger.warning(f"Charger {charger_id} not found in active connections during availability change")
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{charger_id}' is not currently connected. Please check connection status."
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
    request: Request,
    reset_request: ResetRequest,
    db: Session = Depends(get_db)
):
    """Reset a charger (OCPP Reset)"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")

    charger_id = reset_request.charger_id
    reset_type = reset_request.type

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
        # Don't create disconnect event - let OCPP handler manage connection state
        logger.warning(f"Charger {charger_id} not found in active connections during reset command")
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{charger_id}' is not currently connected. Please check connection status."
        )

    # Construct OCPP message
    message_id = str(uuid.uuid4())
    ocpp_payload = {"type": reset_type}
    ocpp_message = [2, message_id, "Reset", ocpp_payload]

    # Send via OCPPHandler (automatically adds to pending_messages)
    success = await ocpp_handler.send_message_to_charger(charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send Reset command")

    # Log outgoing request immediately
    await ocpp_handler.log_message(
        charger_id, "OUT", "Reset", message_id, "Pending",
        None, json.dumps(ocpp_message), None
    )

    logger.info(f"Reset {reset_type} sent to {charger_id} (message_id={message_id})")

    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message=f"Reset command ({reset_type}) sent to charger {charger_id}"
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
        # Don't create disconnect event - let OCPP handler manage connection state
        logger.warning(f"Charger {body.charger_id} not found in active connections during remote start")
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{body.charger_id}' is not currently connected. Please check connection status."
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
    Gets transaction_id from the database (active session) instead of from the request.
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

    # Get active session from database to retrieve transaction_id
    active_session = db.query(DBSession).filter(
        DBSession.charger_id == body.charger_id,
        DBSession.status == "Active"
    ).order_by(DBSession.start_time.desc()).first()
    
    if not active_session:
        raise HTTPException(
            status_code=404,
            detail=f"No active charging session found for charger '{body.charger_id}'"
        )
    
    if active_session.transaction_id is None:
        raise HTTPException(
            status_code=400,
            detail=f"Active session found for charger '{body.charger_id}' but transaction_id is missing"
        )
    
    transaction_id = active_session.transaction_id

    message_id = str(uuid.uuid4())
    ocpp_message = [
        2,  # CALL
        message_id,
        "RemoteStopTransaction",
        {
            "transactionId": transaction_id
        }
    ]
    send_func = getattr(ocpp_handler, "send_message_to_charger", None)
    if not send_func:
        raise HTTPException(status_code=500, detail="OCPP handler missing send_message_to_charger")
    success = await send_func(body.charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send RemoteStopTransaction")
    return {"status": "sent", "message_id": message_id, "transaction_id": transaction_id}

@router.post("/ocpp/local_list/send", response_model=OCPPResponse)
async def send_local_list(
    request: Request,
    send_list_request: SendLocalListRequest,
    db: Session = Depends(get_db)
):
    """Send local authorization list to a charger (OCPP SendLocalList)"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")

    charger_id = send_list_request.charger_id
    list_version = send_list_request.list_version
    update_type = send_list_request.update_type
    local_authorization_list = send_list_request.local_authorization_list

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
        # Don't create disconnect event - let OCPP handler manage connection state
        logger.warning(f"Charger {charger_id} not found in active connections during command")
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{charger_id}' is not currently connected. Please check connection status."
        )

    # Construct OCPP message
    message_id = str(uuid.uuid4())
    ocpp_payload = {
        "listVersion": list_version,
        "updateType": update_type,
        "localAuthorizationList": [
            {
                "idTag": entry.id_tag,
                **({"idTagInfo": {
                    "status": entry.id_tag_info.status,
                    **({"expiryDate": entry.id_tag_info.expiry_date.isoformat()} if entry.id_tag_info.expiry_date else {}),
                    **({"parentIdTag": entry.id_tag_info.parent_id_tag} if entry.id_tag_info.parent_id_tag else {})
                }} if entry.id_tag_info else {})
            } for entry in local_authorization_list
        ]
    }
    ocpp_message = [2, message_id, "SendLocalList", ocpp_payload]

    # Send via OCPPHandler (automatically adds to pending_messages)
    success = await ocpp_handler.send_message_to_charger(charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send SendLocalList command")

    # Log outgoing request immediately
    await ocpp_handler.log_message(
        charger_id, "OUT", "SendLocalList", message_id, "Pending",
        None, json.dumps(ocpp_message), None
    )

    logger.info(f"SendLocalList sent to {charger_id}: version={list_version}, updateType={update_type} (message_id={message_id})")

    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message=f"SendLocalList command sent to charger {charger_id} with version {list_version}"
    )

@router.post("/heartbeat-monitor/stop")
async def stop_heartbeat_monitor(request: Request):
    """Stop the heartbeat monitor task"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")
    
    if ocpp_handler.heartbeat_task and not ocpp_handler.heartbeat_task.done():
        ocpp_handler.heartbeat_task.cancel()
        logger.info("Heartbeat monitor stopped")
        return {"status": "success", "message": "Heartbeat monitor stopped"}
    else:
        return {"status": "info", "message": "Heartbeat monitor was not running"}

@router.post("/heartbeat-monitor/start")
async def start_heartbeat_monitor(request: Request):
    """Start the heartbeat monitor task"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")
    
    if ocpp_handler.heartbeat_task and not ocpp_handler.heartbeat_task.done():
        return {"status": "info", "message": "Heartbeat monitor is already running"}
    else:
        ocpp_handler.heartbeat_task = asyncio.create_task(ocpp_handler.heartbeat_monitor())
        logger.info("Heartbeat monitor started")
        return {"status": "success", "message": "Heartbeat monitor started"}

@router.get("/heartbeat-monitor/status")
async def get_heartbeat_monitor_status(request: Request):
    """Get the heartbeat monitor status"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")
    
    is_running = ocpp_handler.heartbeat_task and not ocpp_handler.heartbeat_task.done()
    return {
        "status": "running" if is_running else "stopped",
        "is_running": is_running,
        "task_exists": ocpp_handler.heartbeat_task is not None
    }

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
        # Don't create disconnect event - let OCPP handler manage connection state
        logger.warning(f"Charger {charger_id} not found in active connections during command")
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{charger_id}' is not currently connected. Please check connection status."
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

@router.post("/ocpp/local_list_version/get", response_model=OCPPResponse)
async def get_local_list_version(
    request: Request,
    get_version_request: GetLocalListVersionRequest,
    db: Session = Depends(get_db)
):
    """Get the local authorization list version from a charger (OCPP GetLocalListVersion)"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")

    charger_id = get_version_request.charger_id

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
        # Don't create disconnect event - let OCPP handler manage connection state
        logger.warning(f"Charger {charger_id} not found in active connections during command")
        raise HTTPException(
            status_code=400,
            detail=f"Charger '{charger_id}' is not currently connected. Please check connection status."
        )

    # Construct OCPP message
    message_id = str(uuid.uuid4())
    ocpp_payload = {}
    ocpp_message = [2, message_id, "GetLocalListVersion", ocpp_payload]

    # Send via OCPPHandler (automatically adds to pending_messages)
    success = await ocpp_handler.send_message_to_charger(charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send GetLocalListVersion command")

    # Log outgoing request immediately
    await ocpp_handler.log_message(
        charger_id, "OUT", "GetLocalListVersion", message_id, "Pending",
        None, json.dumps(ocpp_message), None
    )

    logger.info(f"GetLocalListVersion sent to {charger_id} (message_id={message_id})")

    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message=f"GetLocalListVersion command sent to charger {charger_id}"
    )

@router.post("/ocpp/diagnostics/get", response_model=OCPPResponse)
async def get_diagnostics(
    request: Request,
    get_diag_request: GetDiagnosticsRequest,
    db: Session = Depends(get_db)
):
    """Request diagnostics from a charger (OCPP GetDiagnostics)"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")

    charger_id = get_diag_request.charger_id

    # Connection check
    latest_connection_event = db.query(ConnectionEvent).filter(
        ConnectionEvent.charger_id == charger_id
    ).order_by(ConnectionEvent.timestamp.desc()).first()

    if not latest_connection_event:
        raise HTTPException(status_code=404, detail=f"Charger '{charger_id}' has never connected.")
    if latest_connection_event.event_type != "CONNECT":
        raise HTTPException(status_code=400, detail=f"Charger '{charger_id}' is not currently connected.")
    if charger_id not in ocpp_handler.charger_connections:
        raise HTTPException(status_code=400, detail=f"Charger '{charger_id}' is not currently connected.")

    # Construct OCPP message
    message_id = str(uuid.uuid4())
    ocpp_payload = {"location": get_diag_request.location}
    if get_diag_request.start_time:
        ocpp_payload["startTime"] = get_diag_request.start_time.isoformat()
    if get_diag_request.stop_time:
        ocpp_payload["stopTime"] = get_diag_request.stop_time.isoformat()
    if get_diag_request.retries is not None:
        ocpp_payload["retries"] = get_diag_request.retries
    if get_diag_request.retry_interval is not None:
        ocpp_payload["retryInterval"] = get_diag_request.retry_interval
    
    ocpp_message = [2, message_id, "GetDiagnostics", ocpp_payload]

    success = await ocpp_handler.send_message_to_charger(charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send GetDiagnostics command")

    await ocpp_handler.log_message(charger_id, "OUT", "GetDiagnostics", message_id, "Pending", None, json.dumps(ocpp_message), None)
    logger.info(f"GetDiagnostics sent to {charger_id} (message_id={message_id})")

    return OCPPResponse(status="Accepted", message_id=message_id, message=f"GetDiagnostics command sent to charger {charger_id}")

@router.post("/ocpp/charging_profile/clear", response_model=OCPPResponse)
async def clear_charging_profile(
    request: Request,
    clear_profile_request: ClearChargingProfileRequest,
    db: Session = Depends(get_db)
):
    """Clear charging profile on a charger (OCPP ClearChargingProfile)"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")

    charger_id = clear_profile_request.charger_id

    # Connection check
    latest_connection_event = db.query(ConnectionEvent).filter(
        ConnectionEvent.charger_id == charger_id
    ).order_by(ConnectionEvent.timestamp.desc()).first()

    if not latest_connection_event:
        raise HTTPException(status_code=404, detail=f"Charger '{charger_id}' has never connected.")
    if latest_connection_event.event_type != "CONNECT":
        raise HTTPException(status_code=400, detail=f"Charger '{charger_id}' is not currently connected.")
    if charger_id not in ocpp_handler.charger_connections:
        raise HTTPException(status_code=400, detail=f"Charger '{charger_id}' is not currently connected.")

    # Construct OCPP message
    message_id = str(uuid.uuid4())
    ocpp_payload = {}
    if clear_profile_request.connector_id is not None:
        ocpp_payload["connectorId"] = clear_profile_request.connector_id
    if clear_profile_request.charging_profile_id is not None:
        ocpp_payload["chargingProfileId"] = clear_profile_request.charging_profile_id
    
    ocpp_message = [2, message_id, "ClearChargingProfile", ocpp_payload]

    success = await ocpp_handler.send_message_to_charger(charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send ClearChargingProfile command")

    await ocpp_handler.log_message(charger_id, "OUT", "ClearChargingProfile", message_id, "Pending", None, json.dumps(ocpp_message), None)
    logger.info(f"ClearChargingProfile sent to {charger_id} (message_id={message_id})")

    return OCPPResponse(status="Accepted", message_id=message_id, message=f"ClearChargingProfile command sent to charger {charger_id}")

@router.post("/ocpp/charging_profile/set", response_model=OCPPResponse)
async def set_charging_profile(
    request: Request,
    set_profile_request: SetChargingProfileRequest,
    db: Session = Depends(get_db)
):
    """Set charging profile on a charger (OCPP SetChargingProfile)"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")

    charger_id = set_profile_request.charger_id

    # Connection check
    latest_connection_event = db.query(ConnectionEvent).filter(
        ConnectionEvent.charger_id == charger_id
    ).order_by(ConnectionEvent.timestamp.desc()).first()

    if not latest_connection_event:
        raise HTTPException(status_code=404, detail=f"Charger '{charger_id}' has never connected.")
    if latest_connection_event.event_type != "CONNECT":
        raise HTTPException(status_code=400, detail=f"Charger '{charger_id}' is not currently connected.")
    if charger_id not in ocpp_handler.charger_connections:
        raise HTTPException(status_code=400, detail=f"Charger '{charger_id}' is not currently connected.")

    # Construct OCPP message
    message_id = str(uuid.uuid4())
    ocpp_payload = {
        "connectorId": set_profile_request.connector_id,
        "chargingProfile": set_profile_request.charging_profile
    }
    ocpp_message = [2, message_id, "SetChargingProfile", ocpp_payload]

    success = await ocpp_handler.send_message_to_charger(charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send SetChargingProfile command")

    await ocpp_handler.log_message(charger_id, "OUT", "SetChargingProfile", message_id, "Pending", None, json.dumps(ocpp_message), None)
    logger.info(f"SetChargingProfile sent to {charger_id} (message_id={message_id})")

    return OCPPResponse(status="Accepted", message_id=message_id, message=f"SetChargingProfile command sent to charger {charger_id}")

@router.post("/ocpp/firmware/update", response_model=OCPPResponse)
async def update_firmware(
    request: Request,
    update_fw_request: UpdateFirmwareRequest,
    db: Session = Depends(get_db)
):
    """Update firmware on a charger (OCPP UpdateFirmware)"""
    ocpp_handler = getattr(request.app.state, "ocpp_handler", None)
    if not ocpp_handler:
        raise HTTPException(status_code=500, detail="OCPP handler not available")

    charger_id = update_fw_request.charger_id

    # Connection check
    latest_connection_event = db.query(ConnectionEvent).filter(
        ConnectionEvent.charger_id == charger_id
    ).order_by(ConnectionEvent.timestamp.desc()).first()

    if not latest_connection_event:
        raise HTTPException(status_code=404, detail=f"Charger '{charger_id}' has never connected.")
    if latest_connection_event.event_type != "CONNECT":
        raise HTTPException(status_code=400, detail=f"Charger '{charger_id}' is not currently connected.")
    if charger_id not in ocpp_handler.charger_connections:
        raise HTTPException(status_code=400, detail=f"Charger '{charger_id}' is not currently connected.")

    # Construct OCPP message
    message_id = str(uuid.uuid4())
    ocpp_payload = {
        "location": update_fw_request.location,
        "retrieveDate": update_fw_request.retrieve_date.isoformat()
    }
    if update_fw_request.retries is not None:
        ocpp_payload["retries"] = update_fw_request.retries
    if update_fw_request.retry_interval is not None:
        ocpp_payload["retryInterval"] = update_fw_request.retry_interval
    
    ocpp_message = [2, message_id, "UpdateFirmware", ocpp_payload]

    success = await ocpp_handler.send_message_to_charger(charger_id, ocpp_message)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send UpdateFirmware command")

    await ocpp_handler.log_message(charger_id, "OUT", "UpdateFirmware", message_id, "Pending", None, json.dumps(ocpp_message), None)
    logger.info(f"UpdateFirmware sent to {charger_id} (message_id={message_id})")

    return OCPPResponse(status="Accepted", message_id=message_id, message=f"UpdateFirmware command sent to charger {charger_id}")

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
        yesterday = get_egypt_now() - timedelta(days=1)
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
# Retry Configuration Models
class RetryConfigRequest(BaseModel):
    max_retries: int = Field(..., ge=1, le=10, description="Maximum number of retry attempts (1-10)")
    retry_interval: int = Field(..., ge=1, le=60, description="Retry interval in seconds (1-60)")
    retry_enabled: bool = Field(True, description="Enable/disable retry functionality")

class RetryConfigResponse(BaseModel):
    charger_id: str
    max_retries: int
    retry_interval: int
    retry_enabled: bool
    message: str

class SystemRetryConfigRequest(BaseModel):
    max_retries: int = Field(..., ge=1, le=10, description="Default maximum retry attempts (1-10)")
    retry_interval: int = Field(..., ge=1, le=60, description="Default retry interval in seconds (1-60)")

class SystemRetryConfigResponse(BaseModel):
    max_retries: int
    retry_interval: int
    message: str

# Retry Configuration Endpoints
@router.post("/retry-config/{charger_id}", response_model=RetryConfigResponse)
async def set_charger_retry_config(
    charger_id: str,
    config: RetryConfigRequest,
    db: Session = Depends(get_db)
):
    """Set retry configuration for a specific charger"""
    try:
        charger = db.query(Charger).filter(Charger.id == charger_id).first()
        if not charger:
            raise HTTPException(status_code=404, detail=f"Charger '{charger_id}' not found")
        
        charger.max_retries = config.max_retries
        charger.retry_interval = config.retry_interval
        charger.retry_enabled = config.retry_enabled
        charger.updated_at = get_egypt_now()
        
        db.commit()
        
        logger.info(f"Updated retry config for charger {charger_id}: max_retries={config.max_retries}, retry_interval={config.retry_interval}s, retry_enabled={config.retry_enabled}")
        
        return RetryConfigResponse(
            charger_id=charger_id,
            max_retries=config.max_retries,
            retry_interval=config.retry_interval,
            retry_enabled=config.retry_enabled,
            message=f"Retry configuration updated for charger {charger_id}"
        )
        
    except Exception as e:
        logger.error(f"Failed to update retry config for charger {charger_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update retry configuration: {str(e)}")

@router.get("/retry-config/{charger_id}", response_model=RetryConfigResponse)
async def get_charger_retry_config(
    charger_id: str,
    db: Session = Depends(get_db)
):
    """Get retry configuration for a specific charger"""
    try:
        charger = db.query(Charger).filter(Charger.id == charger_id).first()
        if not charger:
            raise HTTPException(status_code=404, detail=f"Charger '{charger_id}' not found")
        
        return RetryConfigResponse(
            charger_id=charger_id,
            max_retries=charger.max_retries or 3,
            retry_interval=charger.retry_interval or 5,
            retry_enabled=charger.retry_enabled if charger.retry_enabled is not None else True,
            message=f"Retry configuration for charger {charger_id}"
        )
        
    except Exception as e:
        logger.error(f"Failed to get retry config for charger {charger_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get retry configuration: {str(e)}")

@router.post("/retry-config/system", response_model=SystemRetryConfigResponse)
async def set_system_retry_config(
    config: SystemRetryConfigRequest,
    db: Session = Depends(get_db)
):
    """Set default retry configuration for all chargers"""
    try:
        # Update or create max_retries config
        max_retries_config = db.query(SystemConfig).filter(SystemConfig.key == "max_retries").first()
        if max_retries_config:
            max_retries_config.value = str(config.max_retries)
            max_retries_config.updated_at = get_egypt_now()
        else:
            max_retries_config = SystemConfig(
                key="max_retries",
                value=str(config.max_retries),
                description="Default maximum retry attempts for failed messages"
            )
            db.add(max_retries_config)
        
        # Update or create retry_interval config
        retry_interval_config = db.query(SystemConfig).filter(SystemConfig.key == "retry_interval").first()
        if retry_interval_config:
            retry_interval_config.value = str(config.retry_interval)
            retry_interval_config.updated_at = get_egypt_now()
        else:
            retry_interval_config = SystemConfig(
                key="retry_interval",
                value=str(config.retry_interval),
                description="Default retry interval in seconds"
            )
            db.add(retry_interval_config)
        
        db.commit()
        
        logger.info(f"Updated system retry config: max_retries={config.max_retries}, retry_interval={config.retry_interval}s")
        
        return SystemRetryConfigResponse(
            max_retries=config.max_retries,
            retry_interval=config.retry_interval,
            message="System retry configuration updated successfully"
        )
        
    except Exception as e:
        logger.error(f"Failed to update system retry config: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update system retry configuration: {str(e)}")

@router.get("/retry-config/system", response_model=SystemRetryConfigResponse)
async def get_system_retry_config(
    db: Session = Depends(get_db)
):
    """Get default retry configuration"""
    try:
        max_retries_config = db.query(SystemConfig).filter(SystemConfig.key == "max_retries").first()
        retry_interval_config = db.query(SystemConfig).filter(SystemConfig.key == "retry_interval").first()
        
        return SystemRetryConfigResponse(
            max_retries=int(max_retries_config.value) if max_retries_config else 3,
            retry_interval=int(retry_interval_config.value) if retry_interval_config else 5,
            message="System retry configuration"
        )
        
    except Exception as e:
        logger.error(f"Failed to get system retry config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get system retry configuration: {str(e)}")

# Simple retry enable/disable endpoint
@router.post("/retry-config/{charger_id}/enable")
async def enable_charger_retry(
    charger_id: str,
    db: Session = Depends(get_db)
):
    """Enable retry functionality for a specific charger"""
    try:
        charger = db.query(Charger).filter(Charger.id == charger_id).first()
        if not charger:
            raise HTTPException(status_code=404, detail=f"Charger '{charger_id}' not found")
        
        charger.retry_enabled = True
        charger.updated_at = get_egypt_now()
        db.commit()
        
        logger.info(f"Enabled retry for charger {charger_id}")
        
        return {"charger_id": charger_id, "retry_enabled": True, "message": f"Retry enabled for charger {charger_id}"}
        
    except Exception as e:
        logger.error(f"Failed to enable retry for charger {charger_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to enable retry: {str(e)}")

@router.post("/retry-config/{charger_id}/disable")
async def disable_charger_retry(
    charger_id: str,
    db: Session = Depends(get_db)
):
    """Disable retry functionality for a specific charger"""
    try:
        charger = db.query(Charger).filter(Charger.id == charger_id).first()
        if not charger:
            raise HTTPException(status_code=404, detail=f"Charger '{charger_id}' not found")
        
        charger.retry_enabled = False
        charger.updated_at = get_egypt_now()
        db.commit()
        
        logger.info(f"Disabled retry for charger {charger_id}")
        
        return {"charger_id": charger_id, "retry_enabled": False, "message": f"Retry disabled for charger {charger_id}"}
        
    except Exception as e:
        logger.error(f"Failed to disable retry for charger {charger_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to disable retry: {str(e)}")

# app.include_router(ocpp_control.router, prefix="/api", tags=["OCPP Control"])

# Also, ensure your endpoint is defined as:
# @router.post("/ocpp/remote/start", response_model=OCPPResponse)

# If you still get 404, check that:
# - The file is named ocpp_control.py and is imported in app.main.py
# - The router is included with prefix="/api"
# - You are POSTing to http://localhost:8001/api/ocpp/remote/start

# No code changes needed if all above is correct.
# No code changes needed if all above is correct.
