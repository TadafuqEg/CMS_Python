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

from app.models.database import Charger, Connector, Session, MessageLog, ConnectionEvent, SystemConfig, SessionLocal
from app.core.config import settings, create_ssl_context
from app.services.session_manager import SessionManager
from app.services.mq_bridge import MQBridge

logger = logging.getLogger(__name__)

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
        Mark the pending message as responded.
        """
        if message_id in self.pending_messages:
            self.pending_messages[message_id].response_received = True
            self.pending_messages.pop(message_id, None)
            self.stats["pending_messages"] -= 1
            logger.info(f"Received response for message {message_id} from charger {charger_id}")
        
        db = SessionLocal()
        try:
            await self.log_message(charger_id, "IN", "CallResult", message_id, "Success", None, None, json.dumps(payload))
        finally:
            db.close()

    async def handle_call_error(self, charger_id: str, message_id: str, error_code: str, error_description: str, error_details: Dict[str, Any]):
        """
        Handle CALLERROR message from charging point.
        Mark the pending message as responded.
        """
        if message_id in self.pending_messages:
            self.pending_messages[message_id].response_received = True
            self.pending_messages.pop(message_id, None)
            self.stats["pending_messages"] -= 1
            logger.warning(f"Received error response for message {message_id} from charger {charger_id}: {error_code} - {error_description}")
        
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
        db = SessionLocal()
        try:
            start_time = time()
            response = None
            if action == "BootNotification":
                response = await self.handle_boot_notification(charger_id, payload)
            elif action == "Heartbeat":
                response = await self.handle_heartbeat(charger_id, payload)
            elif action == "StatusNotification":
                response = await self.handle_status_notification(charger_id, payload)
            elif action == "MeterValues":
                response = await self.handle_meter_values(charger_id, payload)
            elif action == "StartTransaction":
                response = await self.handle_start_transaction(charger_id, payload)
            elif action == "StopTransaction":
                response = await self.handle_stop_transaction(charger_id, payload)
            elif action == "Authorize":
                response = await self.handle_authorize(charger_id, payload)
            else:
                response = [4, message_id, "NotImplemented", f"Action {action} not supported", {}]
                self.stats["messages_failed"] += 1

            if self.session_manager:
                await self.session_manager.handle_ocpp_message(charger_id, action, payload, response)
            await self.log_message(charger_id, "IN", action, message_id, "Success" if response and response[0] != 4 else "Error",
                                  time() - start_time, json.dumps(payload), json.dumps(response) if response else None)
            return response
        finally:
            db.close()

    async def handle_boot_notification(self, charger_id: str, payload: Dict[str, Any]) -> List[Any]:
        db = SessionLocal()
        try:
            charger = db.query(Charger).filter(Charger.id == charger_id).first()
            gmt_plus_3 = timezone(timedelta(hours=3))
            if charger:
                charger.vendor = payload.get("chargePointVendor")
                charger.model = payload.get("chargePointModel")
                charger.serial_number = payload.get("chargePointSerialNumber")
                charger.firmware_version = payload.get("firmwareVersion")
                db.commit()
            return [3, payload.get("message_id", str(uuid.uuid4())), {
                
                "currentTime": datetime.now(gmt_plus_3).replace(tzinfo=None).isoformat(),
                "interval": 60,
                "status": "Accepted"
            }]
        finally:
            db.close()

    async def handle_heartbeat(self, charger_id: str, payload: Dict[str, Any]) -> List[Any]:
        db = SessionLocal()
        try:
            charger = db.query(Charger).filter(Charger.id == charger_id).first()
            if charger:
                charger.last_heartbeat = datetime.utcnow()
                db.commit()
            return [3, payload.get("message_id", str(uuid.uuid4())), {
                "currentTime": datetime.utcnow().isoformat() + "Z"
            }]
        finally:
            db.close()

    async def handle_status_notification(self, charger_id: str, payload: Dict[str, Any]) -> List[Any]:
        db = SessionLocal()
        try:
            connector_id = payload.get("connectorId", 0)
            status = payload.get("status")
            error_code = payload.get("errorCode")
            connector = db.query(Connector).filter(Connector.charger_id == charger_id, Connector.connector_id == connector_id).first()
            if connector:
                connector.status = status
                connector.error_code = error_code
                connector.last_updated = datetime.utcnow()
                db.commit()
            return [3, payload.get("message_id", str(uuid.uuid4())), {}]
        finally:
            db.close()

    async def handle_meter_values(self, charger_id: str, payload: Dict[str, Any]) -> List[Any]:
        db = SessionLocal()
        try:
            connector_id = payload.get("connectorId", 0)
            transaction_id = payload.get("transactionId")
            for meter_value in payload.get("meterValue", []):
                for sample in meter_value.get("sampledValue", []):
                    if sample.get("measurand") == "Energy.Active.Import.Register":
                        connector = db.query(Connector).filter(Connector.charger_id == charger_id, Connector.connector_id == connector_id).first()
                        if connector:
                            connector.energy_delivered = float(sample.get("value", 0)) / 1000
                            connector.last_updated = datetime.utcnow()
                            db.commit()
            return [3, payload.get("message_id", str(uuid.uuid4())), {}]
        finally:
            db.close()

    async def handle_start_transaction(self, charger_id: str, payload: Dict[str, Any]) -> List[Any]:
        db = SessionLocal()
        try:
            connector_id = payload.get("connectorId", 0)
            id_tag = payload.get("idTag")
            transaction_id = str(uuid.uuid4())
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
            return [3, payload.get("message_id", str(uuid.uuid4())), {
                "transactionId": transaction_id,
                "idTagInfo": {"status": "Accepted"}
            }]
        finally:
            db.close()

    async def handle_stop_transaction(self, charger_id: str, payload: Dict[str, Any]) -> List[Any]:
        db = SessionLocal()
        try:
            transaction_id = payload.get("transactionId")
            session = db.query(Session).filter(Session.transaction_id == transaction_id, Session.charger_id == charger_id).first()
            if session:
                session.stop_time = datetime.utcnow()
                session.meter_stop = payload.get("meterStop")
                session.energy_delivered = (session.meter_stop - session.meter_start) / 1000 if session.meter_start and session.meter_stop else 0
                session.status = "Completed"
                db.commit()
            return [3, payload.get("message_id", str(uuid.uuid4())), {
                "idTagInfo": {"status": "Accepted"}
            }]
        finally:
            db.close()

    async def handle_authorize(self, charger_id: str, payload: Dict[str, Any]) -> List[Any]:
        return [3, payload.get("message_id", str(uuid.uuid4())), {
            "idTagInfo": {"status": "Accepted"}
        }]

    async def send_message_to_charger(self, charger_id: str, message: List[Any], processing_time: float = 0.0) -> bool:
        ws = self.charger_connections.get(charger_id)
        if not ws:
            self.stats["messages_failed"] += 1
            return False

        message_id = message[1] if len(message) > 1 else str(uuid.uuid4())
        start_time = time()
        try:
            await ws.send(json.dumps(message))
            await self.forward_to_masters(charger_id, self.connection_ids.get(charger_id, str(uuid.uuid4())), message, "outgoing", processing_time or (time() - start_time))
            self.stats["messages_sent"] += 1
            if message[0] == 2:
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