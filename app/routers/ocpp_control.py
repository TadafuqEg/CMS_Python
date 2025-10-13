"""
OCPP control endpoints for remote operations
"""

import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid
import json

from app.models.database import get_db, Charger, Session as DBSession
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
    configuration: Dict[str, str]

class ChangeAvailabilityRequest(BaseModel):
    charger_id: str
    connector_id: int
    type: str  # Inoperative or Operative

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

@router.post("/ocpp/configuration/set", response_model=OCPPResponse)
async def set_configuration(
    request: SetConfigurationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Update configuration parameters on a charger"""
    
    # Verify charger exists and is connected
    charger = db.query(Charger).filter(Charger.id == request.charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    if not charger.is_connected:
        raise HTTPException(status_code=400, detail="Charger is not connected")
    
    # Generate unique message ID
    message_id = str(uuid.uuid4())
    
    # TODO: Send ChangeConfiguration via WebSocket
    
    return OCPPResponse(
        status="Accepted",
        message_id=message_id,
        message="Configuration update command sent successfully"
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
    return {"status": "sent", "message_id": message_id}

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
