import asyncio
import json
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Set, Any, Callable
from dataclasses import dataclass, asdict
from time import time
from sqlalchemy import func

import websockets
from websockets.server import WebSocketServerProtocol
from fastapi import WebSocket
from sqlalchemy.orm import Session

from ocpp.routing import on
from ocpp.v16 import call_result
from ocpp.v16.enums import (
    RegistrationStatus,
    AuthorizationStatus,
    AvailabilityStatus,
    ConfigurationStatus,
    ClearCacheStatus,
    DataTransferStatus,
    ResetStatus,
    TriggerMessageStatus,
    DiagnosticsStatus,
    FirmwareStatus,
    GetCompositeScheduleStatus,
    CancelReservationStatus,
    ReservationStatus,
    RemoteStartStopStatus,
)

from app.models.database import Charger, Connector, Session, MessageLog, ConnectionEvent, SystemConfig, SessionLocal
from app.core.config import settings, create_ssl_context
from app.services.session_manager import SessionManager
from app.services.mq_bridge import MQBridge

logger = logging.getLogger(__name__)

def to_camel_case(snake_str: str) -> str:
    """Convert snake_case to camelCase"""
    components = snake_str.split('_')
    return components[0] + ''.join(x.capitalize() for x in components[1:])

def dict_to_camelcase(data: Any) -> Any:
    """Recursively convert dictionary keys from snake_case to camelCase"""
    if isinstance(data, dict):
        return {to_camel_case(k): dict_to_camelcase(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [dict_to_camelcase(item) for item in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    else:
        return data

def asdict_camelcase(obj) -> Dict[str, Any]:
    """Convert dataclass to dict with camelCase keys"""
    return dict_to_camelcase(asdict(obj))

@dataclass
class PendingMessage:
    message_id: str
    charger_id: str
    action: str
    payload: Dict[str, Any]
    timestamp: datetime
    retry_count: int = 0
    max_retries: int = 3
    last_send_attempt: Optional[datetime] = None
    send_successful: bool = False
    callback: Optional[Callable] = None
    response_received: bool = False  # Track if charging point responded
    response_timeout: int = 30  # Timeout in seconds to stop retries

class OCPPHandler:
    def __init__(self, session_manager: Optional[SessionManager], mq_bridge: Optional[MQBridge]):
        self.session_manager = session_manager
        self.mq_bridge = mq_bridge
        self.charger_connections: Dict[str, WebSocketServerProtocol] = {}
        self.connection_ids: Dict[str, str] = {}
        self.transaction_counters: Dict[str, int] = {}  # Track transaction counters per charger
        self.master_connections: Set[WebSocketServerProtocol] = set()
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.pending_messages: Dict[str, PendingMessage] = {}
        self.server = None
        self.message_processor_task = None
        self.retry_task = None
        self.heartbeat_task = None
        self.keepalive_task = None
        self.stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "messages_failed": 0,
            "connections_total": 0,
            "connections_active": 0,
            "master_connections": 0,
            "pending_messages": 0,
            "messages_forwarded": 0  # New metric for forwarded messages
        }

    async def start_websocket_server(self):
        # Use the custom SSL context with specific cipher suite
        ssl_context = create_ssl_context()

        self.server = await websockets.serve(
            self.handle_connection,
            settings.OCPP_WEBSOCKET_HOST,
            settings.OCPP_WEBSOCKET_PORT,
            subprotocols=settings.OCPP_SUBPROTOCOLS,
            ping_interval=120,
            ping_timeout=30,
            close_timeout=10,
            max_size=1024 * 1024,
            ssl=ssl_context
        )
        self.message_processor_task = asyncio.create_task(self.message_processor())
        # self.retry_task = asyncio.create_task(self.retry_pending_messages())
        self.heartbeat_task = asyncio.create_task(self.heartbeat_monitor())
        self.keepalive_task = asyncio.create_task(self.keepalive_monitor())
        logger.info(f"OCPP WebSocket server started on {settings.OCPP_WEBSOCKET_HOST}:{settings.OCPP_WEBSOCKET_PORT}")

    async def stop(self):
        for task in [self.message_processor_task, self.retry_task, self.heartbeat_task, self.keepalive_task]:
            if task:
                task.cancel()
        for ws in list(self.charger_connections.values()) + list(self.master_connections):
            try:
                await ws.close()
            except:
                pass
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        logger.info("OCPP WebSocket server stopped")

    async def handle_connection(self, websocket: WebSocketServerProtocol, path: str):
        try:
            if path.startswith("/ocpp/"):
                charger_id = path.split("/")[-1]
                await self.handle_charger_connection(websocket, charger_id)
            elif path == "/master":
                await self.handle_master_connection(websocket)
            else:
                await websocket.close(code=1002, reason="Invalid path")
        except Exception as e:
            logger.error(f"Error handling connection {path}: {e}")
            try:
                await websocket.close(code=1011, reason=f"Server error: {str(e)}")
            except:
                pass

    async def handle_charger_connection(self, websocket: WebSocketServerProtocol, charger_id: str):
        if charger_id in self.charger_connections:
            await websocket.close(code=1003, reason="Charger ID already connected")
            return

        self.charger_connections[charger_id] = websocket
        self.connection_ids[charger_id] = str(uuid.uuid4())
        self.stats["connections_total"] += 1
        self.stats["connections_active"] += 1

        db = SessionLocal()
        try:
            charger = db.query(Charger).filter(Charger.id == charger_id).first()
            if not charger:
                charger = Charger(id=charger_id, status="Unknown", is_connected=True, last_heartbeat=datetime.utcnow())
                db.add(charger)
            else:
                charger.is_connected = True
                charger.last_heartbeat = datetime.utcnow()
            db.add(ConnectionEvent(charger_id=charger_id, event_type="CONNECT", timestamp=datetime.utcnow()))
            db.commit()
        finally:
            db.close()

        try:
            async for message in websocket:
                start_time = time()
                try:
                    ocpp_message = json.loads(message)
                    logger.info(f"Received message from charger {charger_id}: {message}")
                    await self.forward_to_masters(charger_id, self.connection_ids[charger_id], ocpp_message, "incoming", time() - start_time)
                    await self.handle_charger_message(charger_id, ocpp_message)
                except json.JSONDecodeError:
                    error_msg = {
                        "message_type": "error",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "charger_id": charger_id,
                        "error": "Invalid JSON format",
                        "raw_message": str(message)
                    }
                    await self.forward_to_masters(charger_id, self.connection_ids[charger_id], error_msg, "incoming", time() - start_time)
                    logger.error(f"Invalid JSON from {charger_id}: {message}")
        except websockets.exceptions.ConnectionClosed:
            error_msg = {
                "message_type": "connection_event",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "charger_id": charger_id,
                "event": "disconnected",
                "reason": "WebSocket connection closed"
            }
            await self.forward_to_masters(charger_id, self.connection_ids[charger_id], error_msg, "incoming", 0.0)
        finally:
            self.charger_connections.pop(charger_id, None)
            self.connection_ids.pop(charger_id, None)
            self.stats["connections_active"] -= 1
            db = SessionLocal()
            try:
                charger = db.query(Charger).filter(Charger.id == charger_id).first()
                if charger:
                    charger.is_connected = False
                db.add(ConnectionEvent(charger_id=charger_id, event_type="DISCONNECT", timestamp=datetime.utcnow()))
                db.commit()
            finally:
                db.close()

    async def handle_master_connection(self, websocket: WebSocketServerProtocol):
        self.master_connections.add(websocket)
        self.stats["master_connections"] += 1
        try:
            await websocket.wait_closed()
        finally:
            self.master_connections.discard(websocket)
            self.stats["master_connections"] -= 1

    async def forward_to_masters(self, charger_id: str, connection_id: str, ocpp_message: Any, direction: str, processing_time: float):
        if not self.master_connections:
            return

        forwarded_message = {
            "message_type": "ocpp_forward",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "charger_id": charger_id,
            "connection_id": connection_id,
            "direction": direction,
            "ocpp_message": ocpp_message,
            "processing_time_ms": processing_time * 1000,  # Convert to milliseconds
            "source": "ocpp_handler"
        }

        db = SessionLocal()
        try:
            db.add(MessageLog(
                timestamp=datetime.utcnow(),
                charger_id=charger_id,
                message_type="FORWARD",
                action="ForwardToMaster",
                message_id=ocpp_message[1] if isinstance(ocpp_message, list) and len(ocpp_message) > 1 else str(uuid.uuid4()),
                status="Success",
                request=json.dumps(forwarded_message)
            ))
            db.commit()
        finally:
            db.close()

        disconnected_masters = set()
        for master_ws in self.master_connections:
            try:
                await master_ws.send(json.dumps(forwarded_message))
                self.stats["messages_forwarded"] += 1
            except websockets.exceptions.ConnectionClosed:
                disconnected_masters.add(master_ws)
            except Exception as e:
                logger.error(f"Error forwarding message to master: {e}")

        self.master_connections -= disconnected_masters

    async def handle_call_result(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """
        Handle CALLRESULT message from charging point.
        Mark the pending message as responded and route to specific handler if available.
        """
        action_name = "Unknown"
        if message_id in self.pending_messages:
            pending = self.pending_messages[message_id]
            action_name = pending.action
            self.pending_messages[message_id].response_received = True
            self.pending_messages.pop(message_id, None)
            self.stats["pending_messages"] -= 1
            logger.info(f"Received CALLRESULT for {action_name} (message_id={message_id}) from charger {charger_id}: {payload}")
        
            # Route to specific handler based on action type
            await self.handle_specific_call_result(charger_id, action_name, message_id, payload)
        else:
            logger.info(f"Received CALLRESULT for message {message_id} from charger {charger_id} (not in pending list): {payload}")
        db = SessionLocal()
        try:
            await self.log_message(charger_id, "IN", "CallResult", message_id, "Success", None, None, json.dumps(payload))
        finally:
            db.close()
    
    async def handle_specific_call_result(self, charger_id: str, action: str, message_id: str, payload: Dict[str, Any]):
        """Route CALLRESULT to specific handler based on action type"""
        handler_map = {
            "ChangeAvailability": self.on_change_availability_response,
            "ChangeConfiguration": self.on_change_configuration_response,
            "ClearCache": self.on_clear_cache_response,
            "ClearChargingProfile": self.on_clear_charging_profile_response,
            "GetConfiguration": self.on_get_configuration_response,
            "GetDiagnostics": self.on_get_diagnostics_response,
            "GetLocalListVersion": self.on_get_local_list_version_response,
            "RemoteStartTransaction": self.on_remote_start_transaction_response,
            "RemoteStopTransaction": self.on_remote_stop_transaction_response,
            "Reset": self.on_reset_response,
            "SendLocalList": self.on_send_local_list_response,
            "SetChargingProfile": self.on_set_charging_profile_response,
            "TriggerMessage": self.on_trigger_message_response,
            "UnlockConnector": self.on_unlock_connector_response,
            "UpdateFirmware": self.on_update_firmware_response,
        }
        
        handler = handler_map.get(action)
        if handler:
            await handler(charger_id, message_id, payload)

    async def handle_call_error(self, charger_id: str, message_id: str, error_code: str, error_description: str, error_details: Dict[str, Any]):
        """
        Handle CALLERROR message from charging point.
        Mark the pending message as responded.
        """
        action_name = "Unknown"
        if message_id in self.pending_messages:
            pending = self.pending_messages[message_id]
            action_name = pending.action
            self.pending_messages[message_id].response_received = True
            self.pending_messages.pop(message_id, None)
            self.stats["pending_messages"] -= 1
            logger.warning(f"Received CALLERROR for {action_name} (message_id={message_id}) from charger {charger_id}: {error_code} - {error_description}")
        else:
            logger.warning(f"Received CALLERROR for message {message_id} from charger {charger_id} (not in pending list): {error_code} - {error_description}")
        
        db = SessionLocal()
        try:
            error_data = {"errorCode": error_code, "errorDescription": error_description, "errorDetails": error_details}
            await self.log_message(charger_id, "IN", "CallError", message_id, "Error", None, None, json.dumps(error_data))
        finally:
            db.close()

    async def handle_charger_message(self, charger_id: str, message: List[Any]):
        self.stats["messages_received"] += 1
        start_time = time()
        message_type = message[0]

        try:
            if message_type == 2:
                message_id, action, payload = message[1:4]
                response = await self.handle_incoming_call(charger_id, message_id, action, payload)
                if response:
                    await self.send_message_to_charger(charger_id, response, processing_time=time() - start_time)
            elif message_type == 3:
                message_id, payload = message[1:3]
                logger.info(f"Received CALLRESULT from charger {charger_id}: message_id={message_id}, payload={payload}")
                await self.handle_call_result(charger_id, message_id, payload)
            elif message_type == 4:
                message_id, error_code, error_description, error_details = message[1:5]
                await self.handle_call_error(charger_id, message_id, error_code, error_description, error_details)
            else:
                logger.warning(f"Unknown message type {message_type} from {charger_id}")
        except Exception as e:
            logger.error(f"Error processing message from {charger_id}: {e}")
            self.stats["messages_failed"] += 1
            error_response = [4, message[1] if len(message) > 1 else str(uuid.uuid4()), "FormatViolation", str(e), {}]
            await self.send_message_to_charger(charger_id, error_response, processing_time=time() - start_time)

    async def handle_incoming_call(self, charger_id: str, message_id: str, action: str, payload: Dict[str, Any]) -> Optional[List[Any]]:
        """
        Handle incoming CALL messages from charger (CP → CS).
        
        Handled messages (CP → CS):
        - Authorize: User authorization
        - BootNotification: Charger registration
        - CancelReservation: Cancel a reservation
        - DataTransfer: Vendor-specific data exchange
        - DiagnosticsStatusNotification: Diagnostics status update
        - FirmwareStatusNotification: Firmware update status
        - GetCompositeSchedule: Request composite charging schedule
        - Heartbeat: Connection keep-alive
        - MeterValues: Energy consumption data
        - RemoteStartTransaction: Remote start charging request
        - RemoteStopTransaction: Remote stop charging request
        - ReserveNow: Reserve a connector
        - StartTransaction: Begin charging session
        - StatusNotification: Status changes
        - StopTransaction: End charging session
        - TriggerMessage: Response to trigger message request
        
        CS → CP messages are sent via API endpoints in ocpp_control.py:
        - ChangeAvailability, ChangeConfiguration, ClearCache, ClearChargingProfile
        - GetConfiguration, GetDiagnostics, GetLocalListVersion
        - RemoteStartTransaction, RemoteStopTransaction
        - Reset, SendLocalList, SetChargingProfile, TriggerMessage
        - UnlockConnector, UpdateFirmware
        """
        db = SessionLocal()
        try:
            start_time = time()
            response = None
            if action == "Authorize":
                response = await self.handle_authorize(charger_id, message_id, payload)
            elif action == "BootNotification":
                response = await self.handle_boot_notification(charger_id, message_id, payload)
            elif action == "CancelReservation":
                response = await self.handle_cancel_reservation(charger_id, message_id, payload)
            elif action == "DataTransfer":
                response = await self.handle_data_transfer(charger_id, message_id, payload)
            elif action == "DiagnosticsStatusNotification":
                response = await self.handle_diagnostics_status_notification(charger_id, message_id, payload)
            elif action == "FirmwareStatusNotification":
                response = await self.handle_firmware_status_notification(charger_id, message_id, payload)
            elif action == "GetCompositeSchedule":
                response = await self.handle_get_composite_schedule(charger_id, message_id, payload)
            elif action == "Heartbeat":
                response = await self.handle_heartbeat(charger_id, message_id, payload)
            elif action == "RemoteStartTransaction":
                response = await self.handle_remote_start_transaction(charger_id, message_id, payload)
            elif action == "RemoteStopTransaction":
                response = await self.handle_remote_stop_transaction(charger_id, message_id, payload)
            elif action == "ReserveNow":
                response = await self.handle_reserve_now(charger_id, message_id, payload)
            elif action == "MeterValues":
                response = await self.handle_meter_values(charger_id, message_id, payload)
            elif action == "StartTransaction":
                response = await self.handle_start_transaction(charger_id, message_id, payload)
            elif action == "StatusNotification":
                response = await self.handle_status_notification(charger_id, message_id, payload)
            elif action == "StopTransaction":
                response = await self.handle_stop_transaction(charger_id, message_id, payload)
            elif action == "TriggerMessage":
                response = await self.handle_trigger_message(charger_id, message_id, payload)
            else:
                response = [4, message_id, "NotImplemented", f"Action {action} not supported", {}]
                self.stats["messages_failed"] += 1

            if self.session_manager and response:
                # Extract payload dict from response [3, message_id, payload_dict]
                response_payload = response[2] if len(response) > 2 and isinstance(response, list) else response
                await self.session_manager.handle_ocpp_message(charger_id, action, payload, response_payload)
            await self.log_message(charger_id, "IN", action, message_id, "Success" if response and response[0] != 4 else "Error",
                                  time() - start_time, json.dumps(payload), json.dumps(response) if response else None)
            return response
        finally:
            db.close()

    async def handle_boot_notification(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        db = SessionLocal()
        try:
            charger = db.query(Charger).filter(Charger.id == charger_id).first()
            if charger:
                charger.vendor = payload.get("chargePointVendor")
                charger.model = payload.get("chargePointModel")
                charger.serial_number = payload.get("chargePointSerialNumber")
                charger.firmware_version = payload.get("firmwareVersion")
                db.commit()
            
            # Create proper BootNotificationPayload using OCPP library
            boot_response = call_result.BootNotificationPayload(
                current_time=datetime.now().isoformat(),
                interval=60,
                status=RegistrationStatus.accepted
            )
            
            # Convert dataclass to dict with camelCase keys for JSON serialization
            boot_response_dict = asdict_camelcase(boot_response)
            
            # Return in OCPP message format [3, message_id, payload_dict]
            return [3, message_id, boot_response_dict]
        finally:
            db.close()

    async def handle_heartbeat(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        db = SessionLocal()
        try:
            charger = db.query(Charger).filter(Charger.id == charger_id).first()
            if charger:
                charger.last_heartbeat = datetime.utcnow()
                db.commit()
            
            # Create proper HeartbeatPayload using OCPP library
            heartbeat_response = call_result.HeartbeatPayload(
                current_time=datetime.now().isoformat()
            )
            heartbeat_dict = asdict_camelcase(heartbeat_response)
            
            return [3, message_id, heartbeat_dict]
        finally:
            db.close()

    async def handle_status_notification(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        db = SessionLocal()
        try:
            connector_id = payload.get("connectorId", 0)
            status = payload.get("status")
            error_code = payload.get("errorCode")
            
            # Ensure charger exists in database
            charger = db.query(Charger).filter(Charger.id == charger_id).first()
            if not charger:
                charger = Charger(id=charger_id, status="Unknown", is_connected=True, last_heartbeat=datetime.utcnow())
                db.add(charger)
                db.flush()  # Flush to get the charger ID for foreign key
            
            # Query for existing connector
            connector = db.query(Connector).filter(
                Connector.charger_id == charger_id, 
                Connector.connector_id == connector_id
            ).first()
            
            if connector:
                # Update existing connector
                connector.status = status
                connector.error_code = error_code
                connector.updated_at = datetime.utcnow()
            else:
                # Create new connector
                connector = Connector(
                    charger_id=charger_id,
                    connector_id=connector_id,
                    status=status,
                    error_code=error_code
                )
                db.add(connector)
            
            db.commit()
            logger.info(f"StatusNotification processed for charger {charger_id}, connector {connector_id}: status={status}, error_code={error_code}")
            
            # Create proper StatusNotificationPayload using OCPP library (empty dict)
            status_response = call_result.StatusNotificationPayload()
            status_dict = asdict_camelcase(status_response)
            
            return [3, message_id, status_dict]
        finally:
            db.close()

    async def handle_meter_values(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        db = SessionLocal()
        try:
            connector_id = payload.get("connectorId", 0)
            transaction_id = payload.get("transactionId")
            # Ensure transaction_id is an integer
            if transaction_id is not None:
                transaction_id = int(transaction_id)
            
            for meter_value in payload.get("meterValue", []):
                for sample in meter_value.get("sampledValue", []):
                    if sample.get("measurand") == "Energy.Active.Import.Register":
                        connector = db.query(Connector).filter(Connector.charger_id == charger_id, Connector.connector_id == connector_id).first()
                        if connector:
                            connector.energy_delivered = float(sample.get("value", 0)) / 1000
                            connector.last_updated = datetime.utcnow()
                            db.commit()
            
            # Create proper MeterValuesPayload using OCPP library (empty dict)
            meter_response = call_result.MeterValuesPayload()
            meter_dict = asdict_camelcase(meter_response)
            
            return [3, message_id, meter_dict]
        finally:
            db.close()

    async def handle_start_transaction(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        db = SessionLocal()
        try:
            connector_id = payload.get("connectorId", 0)
            id_tag = payload.get("idTag")
            
            # Initialize transaction counter for charger if not exists
            if charger_id not in self.transaction_counters:
                self.transaction_counters[charger_id] = 0
            
            # Increment and get transaction ID (integer)
            self.transaction_counters[charger_id] += 1
            transaction_id = self.transaction_counters[charger_id]
            
            session = Session(
                charger_id=charger_id,
                connector_id=connector_id,
                transaction_id=transaction_id,
                id_tag=id_tag,
                start_time=datetime.utcnow(),
                status="Active"
            )
            db.add(session)
            db.commit()
            
            # Create proper StartTransactionPayload using OCPP library
            start_response = call_result.StartTransactionPayload(
                transaction_id=transaction_id,
                id_tag_info={'status': AuthorizationStatus.accepted}
            )
            start_dict = asdict_camelcase(start_response)
            
            return [3, message_id, start_dict]
        finally:
            db.close()

    async def handle_stop_transaction(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        db = SessionLocal()
        try:
            transaction_id = payload.get("transactionId")
            # Ensure transaction_id is an integer
            if transaction_id is not None:
                transaction_id = int(transaction_id)
            
            session = db.query(Session).filter(Session.transaction_id == transaction_id, Session.charger_id == charger_id).first()
            if session:
                session.stop_time = datetime.utcnow()
                session.meter_stop = payload.get("meterStop")
                session.energy_delivered = (session.meter_stop - session.meter_start) / 1000 if session.meter_start and session.meter_stop else 0
                session.status = "Completed"
                db.commit()
            
            # Create proper StopTransactionPayload using OCPP library
            stop_response = call_result.StopTransactionPayload(
                id_tag_info={'status': AuthorizationStatus.accepted}
            )
            stop_dict = asdict_camelcase(stop_response)
            
            return [3, message_id, stop_dict]
        finally:
            db.close()

    async def handle_authorize(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        # Create proper AuthorizePayload using OCPP library
        authorize_response = call_result.AuthorizePayload(
            id_tag_info={'status': AuthorizationStatus.accepted}
        )
        authorize_dict = asdict_camelcase(authorize_response)
        
        return [3, message_id, authorize_dict]

    async def handle_data_transfer(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        """Handle DataTransfer message from charger"""
        vendor_id = payload.get("vendorId")
        data = payload.get("data")
        vendor_message_id = payload.get("messageId")
        
        logger.info(f"Received DataTransfer from {charger_id}: vendor_id={vendor_id}, message_id={vendor_message_id}, data={data}")
        
        # Handle malformed JSON in data field (similar to central_system.py)
        if isinstance(data, str):
            try:
                json.loads(data)
                logger.info(f"DataTransfer data is valid JSON: {data}")
            except json.JSONDecodeError as json_err:
                logger.warning(f"DataTransfer contains invalid JSON in data field: {json_err}")
                logger.warning(f"Raw data: {data}")
                # Still accept the message but log the issue
        
        # Create proper DataTransferPayload using OCPP library
        data_transfer_response = call_result.DataTransferPayload(
            status=DataTransferStatus.accepted
        )
        data_transfer_dict = asdict_camelcase(data_transfer_response)
        
        return [3, message_id, data_transfer_dict]

    async def handle_diagnostics_status_notification(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        """Handle DiagnosticsStatusNotification message from charger"""
        status = payload.get("status")
        logger.info(f"Received DiagnosticsStatusNotification from {charger_id}: status={status}")
        
        response = call_result.DiagnosticsStatusNotificationPayload()
        response_dict = asdict_camelcase(response)
        
        return [3, message_id, response_dict]

    async def handle_firmware_status_notification(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        """Handle FirmwareStatusNotification message from charger"""
        status = payload.get("status")
        logger.info(f"Received FirmwareStatusNotification from {charger_id}: status={status}")
        
        response = call_result.FirmwareStatusNotificationPayload()
        response_dict = asdict_camelcase(response)
        
        return [3, message_id, response_dict]

    async def handle_get_composite_schedule(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        """Handle GetCompositeSchedule message from charger"""
        connector_id = payload.get("connectorId")
        duration = payload.get("duration")
        charging_rate_unit = payload.get("chargingRateUnit")
        
        logger.info(f"Received GetCompositeSchedule from {charger_id}: connector_id={connector_id}, duration={duration}")
        
        response = call_result.GetCompositeSchedulePayload(
            status=GetCompositeScheduleStatus.accepted,
            connector_id=connector_id,
            schedule_start=datetime.now().isoformat(),
            charging_schedule={
                "chargingRateUnit": charging_rate_unit or "W",
                "chargingSchedulePeriod": [
                    {
                        "startPeriod": 0,
                        "limit": 10000  # 10 kW
                    }
                ]
            }
        )
        response_dict = asdict_camelcase(response)
        
        return [3, message_id, response_dict]

    async def handle_remote_start_transaction(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        """Handle RemoteStartTransaction message from charger"""
        id_tag = payload.get("idTag")
        connector_id = payload.get("connectorId")
        logger.info(f"Received RemoteStartTransaction from {charger_id}: id_tag={id_tag}, connector_id={connector_id}")
        
        response = call_result.RemoteStartTransactionPayload(
            status=RemoteStartStopStatus.accepted
        )
        response_dict = asdict_camelcase(response)
        
        return [3, message_id, response_dict]

    async def handle_remote_stop_transaction(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        """Handle RemoteStopTransaction message from charger"""
        transaction_id = payload.get("transactionId")
        logger.info(f"Received RemoteStopTransaction from {charger_id}: transaction_id={transaction_id}")
        
        response = call_result.RemoteStopTransactionPayload(
            status=RemoteStartStopStatus.accepted
        )
        response_dict = asdict_camelcase(response)
        
        return [3, message_id, response_dict]

    async def handle_cancel_reservation(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        """Handle CancelReservation message from charger"""
        reservation_id = payload.get("reservationId")
        logger.info(f"Received CancelReservation from {charger_id}: reservation_id={reservation_id}")
        
        response = call_result.CancelReservationPayload(
            status=CancelReservationStatus.accepted
        )
        response_dict = asdict_camelcase(response)
        
        return [3, message_id, response_dict]

    async def handle_reserve_now(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        """Handle ReserveNow message from charger"""
        connector_id = payload.get("connectorId")
        expiry_date = payload.get("expiryDate")
        id_tag = payload.get("idTag")
        reservation_id = payload.get("reservationId")
        
        logger.info(f"Received ReserveNow from {charger_id}: connector_id={connector_id}, reservation_id={reservation_id}, expiry={expiry_date}")
        
        response = call_result.ReserveNowPayload(
            status=ReservationStatus.accepted
        )
        response_dict = asdict_camelcase(response)
        
        return [3, message_id, response_dict]

    async def handle_trigger_message(self, charger_id: str, message_id: str, payload: Dict[str, Any]) -> List[Any]:
        """Handle TriggerMessage response from charger"""
        requested_message = payload.get("requestedMessage")
        connector_id = payload.get("connectorId", 0)
        status = payload.get("status")
        
        logger.info(f"Received TriggerMessage response from {charger_id}: status={status}, message={requested_message}, connector={connector_id}")
        
        # This is a response to a TriggerMessage sent by the central system
        # So we just acknowledge it
        response = call_result.TriggerMessagePayload(
            status=TriggerMessageStatus.accepted
        )
        response_dict = asdict_camelcase(response)
        
        return [3, message_id, response_dict]

    # Response handlers for CS → CP messages
    async def on_change_availability_response(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """Handle response to ChangeAvailability command"""
        status = payload.get("status")
        logger.info(f"ChangeAvailability response from {charger_id}: status={status}")

    async def on_change_configuration_response(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """Handle response to ChangeConfiguration command"""
        status = payload.get("status")
        logger.info(f"ChangeConfiguration response from {charger_id}: status={status}")

    async def on_clear_cache_response(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """Handle response to ClearCache command"""
        status = payload.get("status")
        logger.info(f"ClearCache response from {charger_id}: status={status}")

    async def on_clear_charging_profile_response(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """Handle response to ClearChargingProfile command"""
        status = payload.get("status")
        logger.info(f"ClearChargingProfile response from {charger_id}: status={status}")

    async def on_get_configuration_response(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """Handle response to GetConfiguration command"""
        configuration_key = payload.get("configurationKey")
        unknown_key = payload.get("unknownKey")
        logger.info(f"GetConfiguration response from {charger_id}: keys={len(configuration_key or [])}, unknown={len(unknown_key or [])}")

    async def on_get_diagnostics_response(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """Handle response to GetDiagnostics command"""
        file_name = payload.get("fileName")
        logger.info(f"GetDiagnostics response from {charger_id}: fileName={file_name}")

    async def on_get_local_list_version_response(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """Handle response to GetLocalListVersion command"""
        list_version = payload.get("listVersion")
        logger.info(f"GetLocalListVersion response from {charger_id}: version={list_version}")

    async def on_remote_start_transaction_response(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """Handle response to RemoteStartTransaction command"""
        status = payload.get("status")
        logger.info(f"RemoteStartTransaction response from {charger_id}: status={status}")

    async def on_remote_stop_transaction_response(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """Handle response to RemoteStopTransaction command"""
        status = payload.get("status")
        logger.info(f"RemoteStopTransaction response from {charger_id}: status={status}")

    async def on_reset_response(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """Handle response to Reset command"""
        status = payload.get("status")
        logger.info(f"Reset response from {charger_id}: status={status}")

    async def on_send_local_list_response(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """Handle response to SendLocalList command"""
        status = payload.get("status")
        logger.info(f"SendLocalList response from {charger_id}: status={status}")

    async def on_set_charging_profile_response(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """Handle response to SetChargingProfile command"""
        status = payload.get("status")
        logger.info(f"SetChargingProfile response from {charger_id}: status={status}")

    async def on_trigger_message_response(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """Handle response to TriggerMessage command"""
        status = payload.get("status")
        logger.info(f"TriggerMessage response from {charger_id}: status={status}")

    async def on_unlock_connector_response(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """Handle response to UnlockConnector command"""
        status = payload.get("status")
        logger.info(f"UnlockConnector response from {charger_id}: status={status}")

    async def on_update_firmware_response(self, charger_id: str, message_id: str, payload: Dict[str, Any]):
        """Handle response to UpdateFirmware command"""
        logger.info(f"UpdateFirmware response from {charger_id}")

    async def send_message_to_charger(self, charger_id: str, message: List[Any], processing_time: float = 0.0) -> bool:
        ws = self.charger_connections.get(charger_id)
        if not ws:
            logger.error(f"No WebSocket connection found for charger {charger_id}")
            self.stats["messages_failed"] += 1
            return False

        message_id = message[1] if len(message) > 1 else str(uuid.uuid4())
        start_time = time()
        try:
            message_json = json.dumps(message)
            logger.info(f"Sending message to charger {charger_id}: {message_json}")
            await ws.send(message_json)
            await self.forward_to_masters(charger_id, self.connection_ids.get(charger_id, str(uuid.uuid4())), message, "outgoing", processing_time or (time() - start_time))
            self.stats["messages_sent"] += 1
            if message[0] == 2:
                action = message[2] if len(message) > 2 else "Unknown"
                logger.info(f"Added message to pending queue for charger {charger_id}: message_id={message_id}, action={action}")
                self.pending_messages[message_id] = PendingMessage(
                    message_id=message_id,
                    charger_id=charger_id,
                    action=message[2],
                    payload=message[3],
                    timestamp=datetime.utcnow()
                )
                self.stats["pending_messages"] += 1
            return True
        except Exception as e:
            logger.error(f"Error sending message to {charger_id}: {e}")
            self.stats["messages_failed"] += 1
            return False

    async def broadcast_to_chargers(self, message: List[Any]):
        message_id = message[1] if len(message) > 1 else str(uuid.uuid4())
        start_time = time()
        for charger_id, ws in list(self.charger_connections.items()):
            try:
                await ws.send(json.dumps(message))
                await self.forward_to_masters(charger_id, self.connection_ids.get(charger_id, str(uuid.uuid4())), message, "outgoing", time() - start_time)
                self.stats["messages_sent"] += 1
            except Exception as e:
                logger.error(f"Error broadcasting to {charger_id}: {e}")
                self.stats["messages_failed"] += 1

    async def message_processor(self):
        while True:
            try:
                await asyncio.sleep(1)
                # Placeholder for message queue processing
            except asyncio.CancelledError:
                break

    async def retry_pending_messages(self):
        while True:
            try:
                db = SessionLocal()
                try:
                    retry_config = db.query(SystemConfig).filter(SystemConfig.key == "retry_config").first()
                    retry_config = json.loads(retry_config.value) if retry_config else {"max_retries": 3, "retry_interval": 30}
                finally:
                    db.close()

                for message_id, pending_msg in list(self.pending_messages.items()):
                    # Check if charging point has responded - stop retrying
                    if pending_msg.response_received:
                        logger.info(f"Message {message_id} received response, removing from retry queue")
                        self.pending_messages.pop(message_id, None)
                        self.stats["pending_messages"] -= 1
                        continue
                    
                    # Check if max retries reached - stop retrying
                    if pending_msg.retry_count >= pending_msg.max_retries:
                        logger.warning(f"Message {message_id} reached max retries ({pending_msg.max_retries}), stopping retries")
                        self.pending_messages.pop(message_id, None)
                        self.stats["pending_messages"] -= 1
                        continue
                    
                    # Check if timeout elapsed - stop retrying
                    time_elapsed = (datetime.utcnow() - pending_msg.timestamp).total_seconds()
                    if time_elapsed > pending_msg.response_timeout:
                        logger.warning(f"Message {message_id} timed out after {pending_msg.response_timeout}s, stopping retries")
                        self.pending_messages.pop(message_id, None)
                        self.stats["pending_messages"] -= 1
                        continue
                    
                    # Check if charger is disconnected - stop retrying
                    if pending_msg.charger_id not in self.charger_connections:
                        logger.warning(f"Charger {pending_msg.charger_id} is disconnected, stopping retries for message {message_id}")
                        self.pending_messages.pop(message_id, None)
                        self.stats["pending_messages"] -= 1
                        continue
                    
                    # Check if retry interval has elapsed
                    if pending_msg.last_send_attempt and (datetime.utcnow() - pending_msg.last_send_attempt).total_seconds() < retry_config["retry_interval"]:
                        continue
                    
                    # Retry the message
                    pending_msg.retry_count += 1
                    pending_msg.last_send_attempt = datetime.utcnow()
                    success = await self.send_message_to_charger(charger_id=pending_msg.charger_id, message=[2, message_id, pending_msg.action, pending_msg.payload])
                    pending_msg.send_successful = success
                    if not success:
                        logger.warning(f"Retry {pending_msg.retry_count}/{pending_msg.max_retries} failed for message {message_id}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in retry task: {e}")
            await asyncio.sleep(10)

    async def heartbeat_monitor(self):
        while True:
            try:
                db = SessionLocal()
                try:
                    chargers = db.query(Charger).all()
                    for charger in chargers:
                        if charger.is_connected and (datetime.utcnow() - charger.last_heartbeat).total_seconds() > 600:
                            charger.is_connected = False
                            db.add(ConnectionEvent(charger_id=charger.id, event_type="TIMEOUT", timestamp=datetime.utcnow()))
                            db.commit()
                        # Removed heartbeat sending logic - only charging points should send heartbeats
                        # The central system should only monitor for received heartbeats
                finally:
                    db.close()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
            await asyncio.sleep(60)

    async def keepalive_monitor(self):
        while True:
            try:
                disconnected = []
                for charger_id, ws in list(self.charger_connections.items()):
                    if ws.closed:
                        disconnected.append(charger_id)
                for charger_id in disconnected:
                    self.charger_connections.pop(charger_id, None)
                    self.connection_ids.pop(charger_id, None)
                    self.stats["connections_active"] -= 1
                    db = SessionLocal()
                    try:
                        charger = db.query(Charger).filter(Charger.id == charger_id).first()
                        if charger:
                            charger.is_connected = False
                        db.add(ConnectionEvent(charger_id=charger_id, event_type="DISCONNECT", timestamp=datetime.utcnow()))
                        db.commit()
                    finally:
                        db.close()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in keepalive monitor: {e}")
            await asyncio.sleep(10)

    async def log_message(self, charger_id: str, message_type: str, action: str, message_id: str,
                         status: str, processing_time: Optional[float], request: Optional[str], response: Optional[str]):
        db = SessionLocal()
        try:
            log_entry = MessageLog(
                timestamp=datetime.utcnow(),
                charger_id=charger_id,
                message_type=message_type,
                action=action,
                message_id=message_id,
                status=status,
                processing_time=processing_time,
                request=request,
                response=response
            )
            db.add(log_entry)
            db.commit()
        finally:
            db.close()

    def get_stats(self) -> Dict[str, Any]:
        return self.stats.copy()

    def get_connection_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            events = db.query(ConnectionEvent).order_by(ConnectionEvent.timestamp.desc()).limit(limit).all()
            return [asdict(event) for event in events]
        finally:
            db.close()