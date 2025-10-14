"""
Enhanced OCPP WebSocket handler with message queuing and retry mechanism
"""
from datetime import timedelta

import asyncio
import json
import logging
import ssl
import time
import uuid
from datetime import datetime
from typing import Dict, Set, Optional, Any, List
from dataclasses import dataclass

import websockets
from websockets.server import WebSocketServerProtocol
from fastapi import WebSocket

from app.models.database import SessionLocal, Charger, Connector, Session as DBSession, MessageLog, ConnectionEvent
from app.core.config import settings

logger = logging.getLogger(__name__)

@dataclass
class PendingMessage:
    """Represents a pending OCPP message waiting for response"""
    message_id: str
    charger_id: str
    action: str
    payload: Dict[str, Any]
    timestamp: datetime
    retry_count: int = 0
    max_retries: int = 3
    callback: Optional[callable] = None

class OCPPHandler:
    """Enhanced OCPP WebSocket handler with message queuing and retry mechanism"""
    
    def __init__(self, session_manager, mq_bridge):
        self.session_manager = session_manager
        self.mq_bridge = mq_bridge
        
        # Connection management
        self.charger_connections: Dict[str, WebSocketServerProtocol] = {}
        self.connection_ids: Dict[str, str] = {}  # Store connection IDs for each charger
        self.master_connections: Set[WebSocketServerProtocol] = set()
        
        # Message queuing
        self.pending_messages: Dict[str, PendingMessage] = {}
        self.message_queue: asyncio.Queue = asyncio.Queue()
        
        # Background tasks
        self.websocket_server = None
        self.message_processor_task = None
        self.retry_task = None
        self.heartbeat_task = None
        
        # Statistics
        self.stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "messages_failed": 0,
            "connections_total": 0,
            "connections_active": 0,
            "master_connections": 0,
            "pending_messages": 0
        }
    
    async def start_websocket_server(self):
        """Start the OCPP WebSocket server"""
        try:
            # Create SSL context if certificates are available
            ssl_context = None
            try:
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ssl_context.load_cert_chain(
                    certfile=settings.SSL_CERTFILE,
                    keyfile=settings.SSL_KEYFILE
                )
                logger.info("SSL context created successfully")
            except Exception as e:
                logger.warning(f"SSL context creation failed: {e}. Running without SSL.")
            
            # Start WebSocket server
            self.websocket_server = await websockets.serve(
                self.handle_connection,
                settings.OCPP_WEBSOCKET_HOST,
                settings.OCPP_WEBSOCKET_PORT,
                subprotocols=settings.OCPP_SUBPROTOCOLS,
                ssl=ssl_context,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )
            
            # Start background tasks
            self.message_processor_task = asyncio.create_task(self.message_processor())
            self.retry_task = asyncio.create_task(self.retry_pending_messages())
            self.heartbeat_task = asyncio.create_task(self.heartbeat_monitor())
            
            logger.info(f"OCPP WebSocket server started on {settings.OCPP_WEBSOCKET_HOST}:{settings.OCPP_WEBSOCKET_PORT}")
            
        except Exception as e:
            logger.error(f"Failed to start OCPP WebSocket server: {e}")
            raise
    
    async def stop(self):
        """Stop the OCPP WebSocket server and cleanup"""
        logger.info("Stopping OCPP WebSocket server...")
        
        # Cancel background tasks
        if self.message_processor_task:
            self.message_processor_task.cancel()
        if self.retry_task:
            self.retry_task.cancel()
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        
        # Close all connections
        for charger_id, websocket in self.charger_connections.items():
            try:
                await websocket.close()
            except Exception as e:
                logger.error(f"Error closing connection for {charger_id}: {e}")
        
        for websocket in self.master_connections:
            try:
                await websocket.close()
            except Exception as e:
                logger.error(f"Error closing master connection: {e}")
        
        # Close WebSocket server
        if self.websocket_server:
            self.websocket_server.close()
            await self.websocket_server.wait_closed()
        
        logger.info("OCPP WebSocket server stopped")
    
    async def handle_connection(self, websocket: WebSocketServerProtocol, path: str):
        """Handle incoming WebSocket connections"""
        try:
            # Determine connection type based on path
            if path.startswith('/master'):
                await self.handle_master_connection(websocket, path)
            else:
                # Extract charger ID from path
                charger_id = path.strip('/').split('/')[-1]
                await self.handle_charger_connection(websocket, charger_id)
                
        except Exception as e:
            logger.error(f"Error handling connection: {e}")
        finally:
            # Cleanup connection
            if websocket in self.charger_connections.values():
                charger_id = next(k for k, v in self.charger_connections.items() if v == websocket)
                connection_id = self.connection_ids.get(charger_id)
                await self.remove_charger_connection(charger_id, connection_id)
            elif websocket in self.master_connections:
                self.master_connections.discard(websocket)
    
    async def handle_charger_connection(self, websocket: WebSocketServerProtocol, charger_id: str):
        """Handle charger WebSocket connection"""
        logger.info(f"Charger {charger_id} connecting...")
        
        # Generate unique connection ID
        connection_id = str(uuid.uuid4())
        
        # Add connection
        self.charger_connections[charger_id] = websocket
        self.connection_ids[charger_id] = connection_id  # Store connection ID
        self.stats["connections_total"] += 1
        self.stats["connections_active"] += 1
        
        # Update charger status in database
        await self.update_charger_connection_status(charger_id, True)
        
        # Log connection event
        await self.log_connection_event(charger_id, "CONNECT", websocket, connection_id=connection_id)
        
        try:
            # Handle messages from charger
            async for message in websocket:
                await self.handle_charger_message(charger_id, message)
                
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Charger {charger_id} disconnected")
        except Exception as e:
            logger.error(f"Error handling charger {charger_id}: {e}")
        finally:
            await self.remove_charger_connection(charger_id, connection_id)
    
    async def handle_master_connection(self, websocket: WebSocketServerProtocol, path: str):
        """Handle master connection for broadcasting"""
        logger.info("Master connection established")
        self.master_connections.add(websocket)
        
        try:
            async for message in websocket:
                logger.info(f"Master connection received message: {message}")
                # Broadcast to all chargers
                await self.broadcast_to_chargers(message)
                
        except websockets.exceptions.ConnectionClosed:
            logger.info("Master connection closed")
        except Exception as e:
            logger.error(f"Error handling master connection: {e}")
        finally:
            self.master_connections.discard(websocket)
    
    async def handle_charger_message(self, charger_id: str, message: str):
        """Handle incoming message from charger"""
        start_time = time.time()
        
        try:
            # Parse OCPP message
            message_data = json.loads(message)
            message_type = message_data[0]  # 2 = CALL, 3 = CALLRESULT, 4 = CALLERROR
            
            if message_type == 2:  # CALL (incoming request)
                await self.handle_incoming_call(charger_id, message_data, start_time)
            elif message_type == 3:  # CALLRESULT (response to our call)
                await self.handle_call_result(charger_id, message_data, start_time)
            elif message_type == 4:  # CALLERROR (error response to our call)
                await self.handle_call_error(charger_id, message_data, start_time)
            
            self.stats["messages_received"] += 1
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from {charger_id}: {e}")
            await self.log_message(charger_id, "IN", "InvalidJSON", None, "Error", None, message)
        except Exception as e:
            logger.error(f"Error processing message from {charger_id}: {e}")
            self.stats["messages_failed"] += 1
    
    async def handle_incoming_call(self, charger_id: str, message_data: list, start_time: float):
        """Handle incoming OCPP call from charger"""
        message_id = message_data[1]
        action = message_data[2]
        payload = message_data[3]
        
        logger.info(f"Received {action} from {charger_id}")
        
        # Process the call based on action
        response = await self.process_ocpp_call(charger_id, action, payload)
        
        # Send response
        if response:
            response_message = [3, message_id, response]  # CALLRESULT
            await self.send_message_to_charger(charger_id, response_message)
        
        # Log the message
        processing_time = (time.time() - start_time) * 1000
        await self.log_message(charger_id, "IN", action, message_id, "Success", processing_time, json.dumps(message_data), json.dumps(response) if response else None)
        
        # Notify session manager
        if self.session_manager:
            await self.session_manager.handle_ocpp_message(charger_id, action, payload, response)
    
    async def handle_call_result(self, charger_id: str, message_data: list, start_time: float):
        """Handle call result from charger"""
        message_id = message_data[1]
        payload = message_data[2]

        pending_msg = self.pending_messages.pop(message_id, None)
        if not pending_msg:
            logger.warning(f"No pending message found for result {message_id} from {charger_id}")
            return

        if pending_msg.callback:
            try:
                await pending_msg.callback(payload)
            except Exception as e:
                logger.error(f"Error in callback for {message_id}: {e}")

        logger.info(f"Received response for {pending_msg.action} from {charger_id}: {payload}")

        # Handle ChangeConfiguration (from previous implementation)
        if pending_msg.action == "ChangeConfiguration":
            status = payload.get("status")
            db = SessionLocal()
            try:
                charger = db.query(Charger).filter(Charger.id == charger_id).first()
                if charger:
                    if status == "Accepted":
                        key = pending_msg.payload.get("key")
                        value = pending_msg.payload.get("value")
                        charger.configuration = charger.configuration or {}
                        old_value = charger.configuration.get(key)
                        charger.configuration[key] = value
                        db.commit()
                        logger.info(f"Configuration updated for {charger_id}: {key} = '{value}' (was '{old_value}')")
                        if self.mq_bridge:
                            await self.mq_bridge.send_event(
                                "configuration_changed",
                                charger_id,
                                {"key": key, "value": value, "old_value": old_value}
                            )
                    else:
                        logger.warning(f"ChangeConfiguration {status} for {charger_id}: key={pending_msg.payload.get('key')}")
                else:
                    logger.error(f"Charger {charger_id} not found for configuration update")
            except Exception as e:
                logger.error(f"Failed to update configuration for {charger_id}: {e}")
            finally:
                db.close()

        # Handle ClearCache
        if pending_msg.action == "ClearCache":
            status = payload.get("status")
            logger.info(f"ClearCache {status} for {charger_id}")
            if status == "Accepted":
                if self.mq_bridge:
                    await self.mq_bridge.send_event(
                        "cache_cleared",
                        charger_id,
                        {"timestamp": datetime.utcnow().isoformat()}
                    )
            else:
                logger.warning(f"ClearCache rejected for {charger_id}")

        processing_time = (time.time() - start_time) * 1000
        await self.log_message(
            charger_id, "OUT", pending_msg.action, message_id, "Success",
            processing_time, None, json.dumps(message_data)
        )
    
    async def handle_call_error(self, charger_id: str, message_data: list, start_time: float):
        """Handle call error from charger"""
        message_id = message_data[1]
        error_code = message_data[2]
        error_description = message_data[3]
        error_details = message_data[4] if len(message_data) > 4 else None

        pending_msg = self.pending_messages.pop(message_id, None)
        if pending_msg:
            logger.error(f"Received error for {pending_msg.action} from {charger_id}: {error_code} - {error_description}")
            if pending_msg.action == "ChangeConfiguration":
                logger.warning(f"ChangeConfiguration failed for {charger_id}: {error_code} - {error_description} (details: {error_details})")

        # Log the message
        processing_time = (time.time() - start_time) * 1000
        await self.log_message(
            charger_id, "OUT", "Error", message_id, "Error",
            processing_time, None, json.dumps(message_data)
        )
    
    async def process_ocpp_call(self, charger_id: str, action: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process OCPP call and return response"""
        # This is a simplified version - in a real implementation,
        # you would have proper OCPP message handlers
        
        if action == "BootNotification":
            return await self.handle_boot_notification(charger_id, payload)
        elif action == "Heartbeat":
            return await self.handle_heartbeat(charger_id, payload)
        elif action == "StatusNotification":
            return await self.handle_status_notification(charger_id, payload)
        elif action == "MeterValues":
            return await self.handle_meter_values(charger_id, payload)
        elif action == "StartTransaction":
            return await self.handle_start_transaction(charger_id, payload)
        elif action == "StopTransaction":
            return await self.handle_stop_transaction(charger_id, payload)
        elif action == "Authorize":
            return await self.handle_authorize(charger_id, payload)
        else:
            logger.warning(f"Unhandled OCPP action: {action}")
            return None
    
    async def handle_boot_notification(self, charger_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle BootNotification"""
        # Update charger information in database
        db = SessionLocal()
        try:
            charger = db.query(Charger).filter(Charger.id == charger_id).first()
            if not charger:
                charger = Charger(id=charger_id)
                db.add(charger)
            
            charger.vendor = payload.get("chargePointVendor")
            charger.model = payload.get("chargePointModel")
            charger.serial_number = payload.get("chargePointSerialNumber")
            charger.firmware_version = payload.get("firmwareVersion")
            charger.status = "Available"
            charger.last_heartbeat = datetime.utcnow()
            charger.connection_time = datetime.utcnow()
            charger.is_connected = True
            
            db.commit()
            
        finally:
            db.close()
        
        return {
            "currentTime": datetime.utcnow().isoformat(),
            "interval": settings.HEARTBEAT_INTERVAL,
            "status": "Accepted"
        }
    
    async def handle_heartbeat(self, charger_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Heartbeat"""
        # Update last heartbeat
        await self.update_charger_heartbeat(charger_id)
        
        return {
            "currentTime": datetime.utcnow().isoformat()
        }
    
    async def handle_status_notification(self, charger_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle StatusNotification"""
        connector_id = payload.get("connectorId", 0)
        status = payload.get("status")
        error_code = payload.get("errorCode")
        
        # Update connector status in database
        db = SessionLocal()
        try:
            connector = db.query(Connector).filter(
                Connector.charger_id == charger_id,
                Connector.connector_id == connector_id
            ).first()
            
            if not connector:
                connector = Connector(
                    charger_id=charger_id,
                    connector_id=connector_id
                )
                db.add(connector)
            
            connector.status = status
            connector.error_code = error_code
            connector.updated_at = datetime.utcnow()
            
            db.commit()
            
        finally:
            db.close()
        
        return {}
    
    async def handle_meter_values(self, charger_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MeterValues"""
        # Process meter values - update session energy if active
        connector_id = payload.get("connectorId", 0)
        transaction_id = payload.get("transactionId")
        meter_value = payload.get("meterValue", [])
        
        if transaction_id and meter_value:
            # Update session with latest meter reading
            db = SessionLocal()
            try:
                session = db.query(DBSession).filter(
                    DBSession.charger_id == charger_id,
                    DBSession.transaction_id == transaction_id,
                    DBSession.status == "Active"
                ).first()
                
                if session:
                    # Extract energy value from meter reading
                    for mv in meter_value:
                        for sample in mv.get("sampledValue", []):
                            if sample.get("measurand") == "Energy.Active.Import.Register":
                                energy_value = float(sample.get("value", 0))
                                session.energy_delivered = energy_value / 1000  # Convert Wh to kWh
                                session.updated_at = datetime.utcnow()
                                break
                    
                    db.commit()
                    
            finally:
                db.close()
        
        return {}
    
    async def handle_start_transaction(self, charger_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle StartTransaction"""
        connector_id = payload.get("connectorId", 0)
        id_tag = payload.get("idTag")
        meter_start = payload.get("meterStart", 0)
        timestamp = payload.get("timestamp")
        
        # Create new session
        db = SessionLocal()
        try:
            # Get next transaction ID
            last_session = db.query(DBSession).filter(
                DBSession.charger_id == charger_id
            ).order_by(DBSession.transaction_id.desc()).first()
            
            transaction_id = (last_session.transaction_id + 1) if last_session else 1
            
            session = DBSession(
                transaction_id=transaction_id,
                charger_id=charger_id,
                connector_id=connector_id,
                id_tag=id_tag,
                meter_start=meter_start,
                status="Active"
            )
            db.add(session)
            db.commit()
            
        finally:
            db.close()
        
        return {
            "transactionId": transaction_id,
            "idTagInfo": {"status": "Accepted"}
        }
    
    async def handle_stop_transaction(self, charger_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle StopTransaction"""
        transaction_id = payload.get("transactionId")
        id_tag = payload.get("idTag")
        meter_stop = payload.get("meterStop", 0)
        timestamp = payload.get("timestamp")
        reason = payload.get("reason")
        
        # Update session
        db = SessionLocal()
        try:
            session = db.query(DBSession).filter(
                DBSession.charger_id == charger_id,
                DBSession.transaction_id == transaction_id
            ).first()
            
            if session:
                session.meter_stop = meter_stop
                session.stop_time = datetime.utcnow()
                session.duration = int((session.stop_time - session.start_time).total_seconds())
                session.energy_delivered = (meter_stop - session.meter_start) / 1000  # Convert Wh to kWh
                session.status = "Completed"
                session.updated_at = datetime.utcnow()
                
                db.commit()
                
        finally:
            db.close()
        
        return {
            "idTagInfo": {"status": "Accepted"}
        }
    
    async def handle_authorize(self, charger_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Authorize"""
        id_tag = payload.get("idTag")
        
        # Simple authorization - always accept
        return {
            "idTagInfo": {"status": "Accepted"}
        }
    
    async def send_message_to_charger(self, charger_id: str, message: list):
        """Send message to specific charger and track CALL messages"""
        if charger_id not in self.charger_connections:
            logger.warning(f"Charger {charger_id} not connected")
            return False

        websocket = self.charger_connections[charger_id]
        try:
            # For CALL messages (type 2), add to pending_messages
            if message[0] == 2:  # CALL
                message_id = message[1]
                action = message[2]
                payload = message[3]
                pending_msg = PendingMessage(
                    message_id=message_id,
                    charger_id=charger_id,
                    action=action,
                    payload=payload,
                    timestamp=datetime.utcnow()
                )
                self.pending_messages[message_id] = pending_msg
                logger.debug(f"Added pending message {message_id} ({action}) for {charger_id}")

            await websocket.send(json.dumps(message))
            self.stats["messages_sent"] += 1
            logger.debug(f"Sent message to {charger_id}: {action if message[0] == 2 else 'unknown'}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message to {charger_id}: {e}")
            self.stats["messages_failed"] += 1
            # Retry logic is handled in retry_pending_messages
            return False
    
    async def broadcast_to_chargers(self, message: str):
        """Broadcast message to all connected chargers"""
        if not self.charger_connections:
            logger.warning("No chargers connected to broadcast to")
            return
        
        tasks = []
        disconnected_chargers = []
        
        for charger_id, websocket in self.charger_connections.items():
            try:
                if not websocket.closed:
                    tasks.append(websocket.send(message))
                else:
                    disconnected_chargers.append(charger_id)
            except Exception as e:
                logger.error(f"Error preparing broadcast for {charger_id}: {e}")
                disconnected_chargers.append(charger_id)
        
        # Remove disconnected chargers
        for charger_id in disconnected_chargers:
            await self.remove_charger_connection(charger_id)
        
        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.info(f"Broadcasted message to {len(tasks)} chargers")
            except Exception as e:
                logger.error(f"Error broadcasting message: {e}")
    
    async def remove_charger_connection(self, charger_id: str, connection_id: str = None):
        """Remove charger connection and update status"""
        if charger_id in self.charger_connections:
            del self.charger_connections[charger_id]
            self.stats["connections_active"] -= 1
        
        # Clean up connection ID
        if charger_id in self.connection_ids:
            stored_connection_id = self.connection_ids[charger_id]
            del self.connection_ids[charger_id]
            # Use stored connection_id if none provided
            if connection_id is None:
                connection_id = stored_connection_id
        
        # Log disconnect event if we have a connection_id
        if connection_id:
            await self.log_connection_event(charger_id, "DISCONNECT", 
                                          reason="Connection removed", 
                                          connection_id=connection_id)
        
        # Update charger status in database
        await self.update_charger_connection_status(charger_id, False)
        
        logger.info(f"Charger {charger_id} removed. Active connections: {len(self.charger_connections)}")
    
    async def update_charger_connection_status(self, charger_id: str, is_connected: bool):
        """Update charger connection status in database"""
        db = SessionLocal()
        try:
            charger = db.query(Charger).filter(Charger.id == charger_id).first()
            if charger:
                charger.is_connected = is_connected
                if is_connected:
                    charger.connection_time = datetime.utcnow()
                    charger.status = "Available"
                else:
                    charger.disconnect_time = datetime.utcnow()
                    charger.status = "Offline"
                charger.updated_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()
    
    async def update_charger_heartbeat(self, charger_id: str):
        """Update charger heartbeat timestamp"""
        db = SessionLocal()
        try:
            charger = db.query(Charger).filter(Charger.id == charger_id).first()
            if charger:
                charger.last_heartbeat = datetime.utcnow()
                charger.updated_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()
    
    async def log_message(self, charger_id: str, message_type: str, action: str, message_id: str, 
                         status: str, processing_time: Optional[float], request: Optional[str], 
                         response: Optional[str]):
        """Log OCPP message to database"""
        db = SessionLocal()
        try:
            log_entry = MessageLog(
                charger_id=charger_id,
                message_type=message_type,
                action=action,
                message_id=message_id,
                request=request,
                response=response,
                status=status,
                processing_time=processing_time
            )
            db.add(log_entry)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to log message: {e}")
        finally:
            db.close()
    
    async def log_connection_event(self, charger_id: str, event_type: str, websocket: WebSocketServerProtocol = None, 
                                  reason: str = None, connection_id: str = None):
        """Log WebSocket connection event to database"""
        db = SessionLocal()
        try:
            # Extract connection information from websocket if available
            remote_address = None
            user_agent = None
            subprotocol = None
            
            if websocket:
                try:
                    remote_address = websocket.remote_address[0] if websocket.remote_address else None
                    user_agent = websocket.request_headers.get('User-Agent')
                    subprotocol = websocket.subprotocol
                except Exception as e:
                    logger.warning(f"Could not extract websocket info: {e}")
            
            # Calculate session duration for disconnect events
            session_duration = None
            if event_type == "DISCONNECT" and connection_id:
                # Try to find the corresponding connect event
                connect_event = db.query(ConnectionEvent).filter(
                    ConnectionEvent.charger_id == charger_id,
                    ConnectionEvent.event_type == "CONNECT",
                    ConnectionEvent.connection_id == connection_id
                ).order_by(ConnectionEvent.timestamp.desc()).first()
                
                if connect_event:
                    session_duration = int((datetime.utcnow() - connect_event.timestamp).total_seconds())
            
            # Create connection event log
            event_log = ConnectionEvent(
                charger_id=charger_id,
                event_type=event_type,
                connection_id=connection_id,
                remote_address=remote_address,
                user_agent=user_agent,
                subprotocol=subprotocol,
                reason=reason,
                session_duration=session_duration,
                event_metadata={
                    "timestamp": datetime.utcnow().isoformat(),
                    "event_source": "ocpp_handler"
                }
            )
            
            db.add(event_log)
            db.commit()
            
            logger.info(f"Logged {event_type} event for charger {charger_id}")
            
        except Exception as e:
            logger.error(f"Failed to log connection event: {e}")
        finally:
            db.close()
    
    async def message_processor(self):
        """Background task to process queued messages"""
        while True:
            try:
                # Process queued messages
                await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in message processor: {e}")
    
    async def retry_pending_messages(self):
        """Background task to retry failed messages"""
        while True:
            try:
                await asyncio.sleep(5)  # Check every 5 seconds
                
                current_time = datetime.utcnow()
                expired_messages = []
                
                for message_id, pending_msg in self.pending_messages.items():
                    # Check if message has expired (30 seconds timeout)
                    if (current_time - pending_msg.timestamp).total_seconds() > 30:
                        expired_messages.append(message_id)
                    elif pending_msg.retry_count < pending_msg.max_retries:
                        # Retry message
                        await self.send_message_to_charger(
                            pending_msg.charger_id,
                            [2, pending_msg.message_id, pending_msg.action, pending_msg.payload]
                        )
                        pending_msg.retry_count += 1
                        pending_msg.timestamp = current_time
                
                # Remove expired messages
                for message_id in expired_messages:
                    if message_id in self.pending_messages:
                        del self.pending_messages[message_id]
                        self.stats["messages_failed"] += 1
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in retry task: {e}")
    
    async def heartbeat_monitor(self):
        """Background task to monitor charger heartbeats"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                current_time = datetime.utcnow()
                timeout_threshold = current_time - timedelta(minutes=5)  # 5 minute timeout
                
                # Check for chargers that haven't sent heartbeat
                db = SessionLocal()
                try:
                    stale_chargers = db.query(Charger).filter(
                        Charger.is_connected == True,
                        Charger.last_heartbeat < timeout_threshold
                    ).all()
                    
                    for charger in stale_chargers:
                        logger.warning(f"Charger {charger.id} heartbeat timeout")
                        charger.status = "Offline"
                        charger.is_connected = False
                        charger.updated_at = current_time
                        
                        # Remove from active connections
                        if charger.id in self.charger_connections:
                            connection_id = self.connection_ids.get(charger.id)
                            await self.remove_charger_connection(charger.id, connection_id)
                    
                    if stale_chargers:
                        db.commit()
                        
                finally:
                    db.close()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get handler statistics"""
        return {
            **self.stats,
            "active_connections": len(self.charger_connections),
            "master_connections": len(self.master_connections),
            "pending_messages": len(self.pending_messages)
        }
    
    def get_connection_events(self, charger_id: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get connection events from database"""
        db = SessionLocal()
        try:
            query = db.query(ConnectionEvent)
            
            if charger_id:
                query = query.filter(ConnectionEvent.charger_id == charger_id)
            
            events = query.order_by(ConnectionEvent.timestamp.desc()).limit(limit).all()
            
            return [
                {
                    "id": event.id,
                    "charger_id": event.charger_id,
                    "event_type": event.event_type,
                    "connection_id": event.connection_id,
                    "remote_address": event.remote_address,
                    "user_agent": event.user_agent,
                    "subprotocol": event.subprotocol,
                    "reason": event.reason,
                    "session_duration": event.session_duration,
                    "timestamp": event.timestamp.isoformat(),
                    "event_metadata": event.event_metadata
                }
                for event in events
            ]
        except Exception as e:
            logger.error(f"Failed to get connection events: {e}")
            return []
        finally:
            db.close()
