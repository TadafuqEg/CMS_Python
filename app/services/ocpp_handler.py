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
from fastapi import WebSocket
from websockets.server import WebSocketServerProtocol

from app.models.database import SessionLocal, Charger, Connector, Session as DBSession, MessageLog, ConnectionEvent, SystemConfig
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
    last_send_attempt: Optional[datetime] = None
    send_successful: bool = False
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
        self.keepalive_task = None
        
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
                ping_interval=120,  # Increased to 120 seconds - much less aggressive pinging
                ping_timeout=60,    # Increased to 60 seconds - more time for pong response
                close_timeout=10,
                max_size=2**20,  # 1MB max message size
                max_queue=32,   # Max queued messages
                read_limit=2**16,  # 64KB read buffer
                write_limit=2**16  # 64KB write buffer
            )
            
            # Start background tasks
            self.message_processor_task = asyncio.create_task(self.message_processor())
            self.retry_task = asyncio.create_task(self.retry_pending_messages())
            self.heartbeat_task = asyncio.create_task(self.heartbeat_monitor())
            self.keepalive_task = asyncio.create_task(self.keepalive_monitor())
            
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
        if self.keepalive_task:
            self.keepalive_task.cancel()
        
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
        
        try:
            # Generate unique connection ID
            connection_id = str(uuid.uuid4())
            
            # Create charger record with default values if it doesn't exist
            await self.create_or_update_charger_on_connect(charger_id, websocket)
            
            # Add connection
            self.charger_connections[charger_id] = websocket
            self.connection_ids[charger_id] = connection_id  # Store connection ID
            self.stats["connections_total"] += 1
            self.stats["connections_active"] += 1
            
            # Update charger status in database
            await self.update_charger_connection_status(charger_id, True)
            
            # Log connection event
            await self.log_connection_event(charger_id, "CONNECT", websocket, connection_id=connection_id)
            
            logger.info(f"Charger {charger_id} connected successfully")
            
        except Exception as e:
            logger.error(f"Error in handle_charger_connection for {charger_id}: {e}")
            raise
        
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
        """Handle incoming messages from charger"""
        self.stats["messages_received"] += 1
        start_time = time.time()
        try:
            logger.debug(f"Raw message received from {charger_id}: {message}")  # Add raw message logging
            message_data = json.loads(message)
            if not isinstance(message_data, list):
                raise ValueError("Invalid OCPP message format: not a list")

            message_type = message_data[0]
            logger.info(f"Processing message type {message_type} from {charger_id}")

            if message_type == 2:  # CALL
                await self.handle_incoming_call(charger_id, message_data, start_time)
            elif message_type == 3:  # CALLRESULT
                await self.handle_call_result(charger_id, message_data, start_time)
            elif message_type == 4:  # CALLERROR
                await self.handle_call_error(charger_id, message_data, start_time)
            else:
                logger.error(f"Unknown message type {message_type} from {charger_id}")
                await self.log_message(
                    charger_id, "IN", "Unknown", None, "Error",
                    (time.time() - start_time) * 1000, message, None
                )
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from {charger_id}: {e}")
            await self.log_message(
                charger_id, "IN", "Invalid", None, "Error",
                (time.time() - start_time) * 1000, message, None
            )
        except Exception as e:
            logger.error(f"Error processing message from {charger_id}: {e}")
            await self.log_message(
                charger_id, "IN", "Error", None, "Error",
                (time.time() - start_time) * 1000, message, None
            )
    
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

        # Handle ChangeConfiguration
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

        # Handle ChangeAvailability
        if pending_msg.action == "ChangeAvailability":
            status = payload.get("status")
            connector_id = pending_msg.payload.get("connectorId")
            availability_type = pending_msg.payload.get("type")
            db = SessionLocal()
            try:
                if status == "Accepted":
                    if connector_id == 0:
                        charger = db.query(Charger).filter(Charger.id == charger_id).first()
                        if charger:
                            old_status = charger.status
                            charger.status = availability_type
                            db.commit()
                            logger.info(f"Charger {charger_id} availability changed to {availability_type} (was {old_status})")
                            if self.mq_bridge:
                                await self.mq_bridge.send_event(
                                    "availability_changed",
                                    charger_id,
                                    {
                                        "connector_id": connector_id,
                                        "type": availability_type,
                                        "old_status": old_status
                                    }
                                )
                        else:
                            logger.error(f"Charger {charger_id} not found for availability update")
                    else:
                        connector = db.query(Connector).filter(
                            Connector.charger_id == charger_id,
                            Connector.connector_id == connector_id
                        ).first()
                        if connector:
                            old_status = connector.status
                            connector.status = availability_type
                            db.commit()
                            logger.info(f"Connector {connector_id} on {charger_id} availability changed to {availability_type} (was {old_status})")
                            if self.mq_bridge:
                                await self.mq_bridge.send_event(
                                    "availability_changed",
                                    charger_id,
                                    {
                                        "connector_id": connector_id,
                                        "type": availability_type,
                                        "old_status": old_status
                                    }
                                )
                        else:
                            logger.error(f"Connector {connector_id} on {charger_id} not found for availability update")
                else:
                    logger.warning(f"ChangeAvailability {status} for {charger_id}, connector {connector_id}")
            except Exception as e:
                logger.error(f"Failed to update availability for {charger_id}, connector {connector_id}: {e}")
            finally:
                db.close()

        # Handle GetConfiguration
        if pending_msg.action == "GetConfiguration":
            configuration_keys = payload.get("configurationKey", [])
            unknown_keys = payload.get("unknownKey", [])
            db = SessionLocal()
            try:
                charger = db.query(Charger).filter(Charger.id == charger_id).first()
                if charger:
                    if configuration_keys:
                        charger.configuration = charger.configuration or {}
                        for config in configuration_keys:
                            key = config.get("key")
                            value = config.get("value")
                            if key and value is not None:
                                charger.configuration[key] = value
                        db.commit()
                        logger.info(f"Updated configuration for {charger_id}: {configuration_keys}")
                    if unknown_keys:
                        logger.warning(f"Unknown configuration keys for {charger_id}: {unknown_keys}")
                    if self.mq_bridge:
                        await self.mq_bridge.send_event(
                            "configuration_retrieved",
                            charger_id,
                            {
                                "configuration_keys": configuration_keys,
                                "unknown_keys": unknown_keys,
                                "requested_keys": pending_msg.payload.get("key", [])
                            }
                        )
                else:
                    logger.error(f"Charger {charger_id} not found for configuration update")
            except Exception as e:
                logger.error(f"Failed to process GetConfiguration response for {charger_id}: {e}")
            finally:
                db.close()

        # Handle Reset
        if pending_msg.action == "Reset":
            status = payload.get("status")
            reset_type = pending_msg.payload.get("type")
            db = SessionLocal()
            try:
                charger = db.query(Charger).filter(Charger.id == charger_id).first()
                if charger:
                    if status == "Accepted":
                        logger.info(f"Reset {reset_type} accepted for {charger_id}")
                        if reset_type == "Hard":
                            old_status = charger.status
                            charger.status = "Unavailable"
                            charger.is_connected = False
                            db.commit()
                            logger.info(f"Charger {charger_id} status set to Unavailable due to Hard reset (was {old_status})")
                        if self.mq_bridge:
                            await self.mq_bridge.send_event(
                                "reset_triggered",
                                charger_id,
                                {
                                    "type": reset_type,
                                    "status": status,
                                    "timestamp": datetime.utcnow().isoformat()
                                }
                            )
                    else:
                        logger.warning(f"Reset {reset_type} {status} for {charger_id}")
                else:
                    logger.error(f"Charger {charger_id} not found for reset")
            except Exception as e:
                logger.error(f"Failed to process Reset response for {charger_id}: {e}")
            finally:
                db.close()

        # Handle UnlockConnector
        if pending_msg.action == "UnlockConnector":
            status = payload.get("status")
            connector_id = pending_msg.payload.get("connectorId")
            db = SessionLocal()
            try:
                connector = db.query(Connector).filter(
                    Connector.charger_id == charger_id,
                    Connector.connector_id == connector_id
                ).first()
                if connector:
                    if status == "Unlocked":
                        if connector.status not in ["Charging", "Occupied"]:
                            old_status = connector.status
                            connector.status = "Available"
                            db.commit()
                            logger.info(f"Connector {connector_id} on {charger_id} unlocked, status set to Available (was {old_status})")
                        else:
                            logger.info(f"Connector {connector_id} on {charger_id} unlocked, but status remains {connector.status} due to active session")
                        if self.mq_bridge:
                            await self.mq_bridge.send_event(
                                "unlock_triggered",
                                charger_id,
                                {
                                    "connector_id": connector_id,
                                    "status": status,
                                    "timestamp": datetime.utcnow().isoformat()
                                }
                            )
                    else:
                        logger.warning(f"UnlockConnector {status} for {charger_id}, connector {connector_id}")
                else:
                    logger.error(f"Connector {connector_id} on {charger_id} not found for unlock")
            except Exception as e:
                logger.error(f"Failed to process UnlockConnector response for {charger_id}, connector {connector_id}: {e}")
            finally:
                db.close()

        # Handle GetLocalListVersion
        if pending_msg.action == "GetLocalListVersion":
            list_version = payload.get("listVersion")
            db = SessionLocal()
            try:
                charger = db.query(Charger).filter(Charger.id == charger_id).first()
                if charger:
                    if list_version is not None:
                        old_version = charger.local_list_version
                        charger.local_list_version = list_version
                        db.commit()
                        logger.info(f"Local list version for {charger_id} updated to {list_version} (was {old_version})")
                        if self.mq_bridge:
                            await self.mq_bridge.send_event(
                                "local_list_version_retrieved",
                                charger_id,
                                {
                                    "list_version": list_version,
                                    "old_version": old_version,
                                    "timestamp": datetime.utcnow().isoformat()
                                }
                            )
                    else:
                        logger.warning(f"No listVersion in GetLocalListVersion response for {charger_id}")
                else:
                    logger.error(f"Charger {charger_id} not found for GetLocalListVersion")
            except Exception as e:
                logger.error(f"Failed to process GetLocalListVersion response for {charger_id}: {e}")
            finally:
                db.close()

        # Handle SendLocalList
        if pending_msg.action == "SendLocalList":
            status = payload.get("status")
            list_version = pending_msg.payload.get("listVersion")
            update_type = pending_msg.payload.get("updateType")
            db = SessionLocal()
            try:
                charger = db.query(Charger).filter(Charger.id == charger_id).first()
                if charger:
                    if status == "Accepted":
                        old_version = charger.local_list_version
                        charger.local_list_version = list_version
                        db.commit()
                        logger.info(f"Local authorization list for {charger_id} updated to version {list_version} (was {old_version}) with {update_type} update")
                        if self.mq_bridge:
                            await self.mq_bridge.send_event(
                                "local_list_updated",
                                charger_id,
                                {
                                    "list_version": list_version,
                                    "old_version": old_version,
                                    "update_type": update_type,
                                    "timestamp": datetime.utcnow().isoformat()
                                }
                            )
                    else:
                        logger.warning(f"SendLocalList {status} for {charger_id}, version {list_version}, updateType {update_type}")
                else:
                    logger.error(f"Charger {charger_id} not found for SendLocalList")
            except Exception as e:
                logger.error(f"Failed to process SendLocalList response for {charger_id}: {e}")
            finally:
                db.close()

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
        """Handle BootNotification and save all WebSocket data"""
        logger.info(f"Handling BootNotification for charger {charger_id} with payload: {payload}")
        
        # Update charger information in database with all BootNotification data
        db = SessionLocal()
        try:
            charger = db.query(Charger).filter(Charger.id == charger_id).first()
            if not charger:
                logger.warning(f"Charger {charger_id} not found in database during BootNotification")
                charger = Charger(id=charger_id)
                db.add(charger)
            
            # Update charger with BootNotification data
            charger.vendor = payload.get("chargePointVendor", charger.vendor)
            charger.model = payload.get("chargePointModel", charger.model)
            charger.serial_number = payload.get("chargePointSerialNumber", charger.serial_number)
            charger.firmware_version = payload.get("firmwareVersion", charger.firmware_version)
            charger.status = "Available"
            charger.last_heartbeat = datetime.utcnow()
            charger.connection_time = datetime.utcnow()
            charger.is_connected = True
            
            # Save all BootNotification payload data in configuration
            if not charger.configuration:
                charger.configuration = {}
            
            # Store all BootNotification data
            charger.configuration.update({
                "boot_notification_data": payload,
                "boot_notification_received_at": datetime.utcnow().isoformat(),
                "charge_point_vendor": payload.get("chargePointVendor"),
                "charge_point_model": payload.get("chargePointModel"),
                "charge_point_serial_number": payload.get("chargePointSerialNumber"),
                "firmware_version": payload.get("firmwareVersion"),
                "charge_box_serial_number": payload.get("chargeBoxSerialNumber"),
                "meter_serial_number": payload.get("meterSerialNumber"),
                "meter_type": payload.get("meterType"),
                "last_boot_time": datetime.utcnow().isoformat()
            })
            
            # Update charger metadata
            charger.updated_at = datetime.utcnow()
            
            db.commit()
            
            logger.info(f"Updated charger {charger_id} with BootNotification data: vendor={charger.vendor}, model={charger.model}, firmware={charger.firmware_version}")
            logger.info(f"Configuration updated with {len(charger.configuration)} fields")
            
        except Exception as e:
            logger.error(f"Failed to update charger {charger_id} with BootNotification: {e}")
            db.rollback()
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
            
            # Mark send as failed for pending messages
            if message[0] == 2:  # CALL
                message_id = message[1]
                if message_id in self.pending_messages:
                    self.pending_messages[message_id].send_successful = False
                    self.pending_messages[message_id].last_send_attempt = datetime.utcnow()
            
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
            
            # Mark send as successful for pending messages
            if message[0] == 2:  # CALL
                message_id = message[1]
                if message_id in self.pending_messages:
                    self.pending_messages[message_id].send_successful = True
                    self.pending_messages[message_id].last_send_attempt = datetime.utcnow()
            
            return True
        except Exception as e:
            logger.error(f"Failed to send message to {charger_id}: {e}")
            self.stats["messages_failed"] += 1
            
            # Mark send as failed for pending messages
            if message[0] == 2:  # CALL
                message_id = message[1]
                if message_id in self.pending_messages:
                    self.pending_messages[message_id].send_successful = False
                    self.pending_messages[message_id].last_send_attempt = datetime.utcnow()
            
            # Clean up stale connection if WebSocket send fails
            logger.warning(f"WebSocket send failed for {charger_id}, cleaning up stale connection")
            await self.remove_charger_connection(charger_id)
            
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
    
    def get_retry_config(self, charger_id: str = None):
        """Get retry configuration from database - charger specific or system default"""
        db = SessionLocal()
        try:
            # Try to get charger-specific retry configuration first
            if charger_id:
                charger = db.query(Charger).filter(Charger.id == charger_id).first()
                if charger and charger.max_retries and charger.retry_interval:
                    return {
                        "max_retries": charger.max_retries,
                        "retry_interval": charger.retry_interval,
                        "retry_enabled": charger.retry_enabled if charger.retry_enabled is not None else True
                    }
            
            # Fall back to system configuration
            max_retries_config = db.query(SystemConfig).filter(SystemConfig.key == "max_retries").first()
            retry_interval_config = db.query(SystemConfig).filter(SystemConfig.key == "retry_interval").first()
            
            return {
                "max_retries": int(max_retries_config.value) if max_retries_config else 3,
                "retry_interval": int(retry_interval_config.value) if retry_interval_config else 5,
                "retry_enabled": True  # Default to enabled for system config
            }
        except Exception as e:
            logger.error(f"Failed to get retry configuration: {e}")
            return {"max_retries": 3, "retry_interval": 5, "retry_enabled": True}  # Default fallback
        finally:
            db.close()
    
    async def create_or_update_charger_on_connect(self, charger_id: str, websocket: WebSocketServerProtocol):
        """Create charger record with default values when WebSocket connects"""
        logger.info(f"Creating/updating charger {charger_id} on connect")
        db = SessionLocal()
        try:
            charger = db.query(Charger).filter(Charger.id == charger_id).first()
            logger.info(f"Charger {charger_id} exists: {charger is not None}")
            
            if not charger:
                # Extract connection information from websocket
                remote_address = None
                user_agent = None
                subprotocol = None
                
                try:
                    remote_address = websocket.remote_address[0] if websocket.remote_address else None
                    user_agent = websocket.request_headers.get('User-Agent')
                    subprotocol = websocket.subprotocol
                    logger.info(f"Extracted websocket info: remote={remote_address}, user_agent={user_agent}, subprotocol={subprotocol}")
                except Exception as e:
                    logger.warning(f"Could not extract websocket info: {e}")
                
                # Create new charger with default values
                charger = Charger(
                    id=charger_id,
                    vendor="Unknown",
                    model="Unknown",
                    serial_number="Unknown",
                    firmware_version="Unknown",
                    status="Connecting",
                    is_connected=True,
                    connection_time=datetime.utcnow(),
                    last_heartbeat=datetime.utcnow(),
                    max_retries=3,  # Default retry attempts
                    retry_interval=5,  # Default retry interval in seconds
                    retry_enabled=True,  # Default retry enabled
                    configuration={
                        "remote_address": remote_address,
                        "user_agent": user_agent,
                        "subprotocol": subprotocol,
                        "connection_source": "websocket"
                    }
                )
                db.add(charger)
                logger.info(f"Created new charger record for {charger_id} with default values")
            else:
                # Update existing charger connection info
                charger.is_connected = True
                charger.connection_time = datetime.utcnow()
                charger.status = "Connecting"
                charger.updated_at = datetime.utcnow()
                
                # Update configuration with connection info
                if not charger.configuration:
                    charger.configuration = {}
                
                try:
                    charger.configuration.update({
                        "remote_address": websocket.remote_address[0] if websocket.remote_address else None,
                        "user_agent": websocket.request_headers.get('User-Agent'),
                        "subprotocol": websocket.subprotocol,
                        "last_connection_time": datetime.utcnow().isoformat()
                    })
                except Exception as e:
                    logger.warning(f"Could not update charger configuration: {e}")
                
                logger.info(f"Updated existing charger record for {charger_id}")
            
            db.commit()
            logger.info(f"Successfully committed charger {charger_id} to database")
            
        except Exception as e:
            logger.error(f"Failed to create/update charger {charger_id}: {e}")
            db.rollback()
        finally:
            db.close()
    
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
        """Background task to retry failed messages using database configuration"""
        while True:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                
                current_time = datetime.utcnow()
                expired_messages = []
                
                for message_id, pending_msg in self.pending_messages.items():
                    # Get retry configuration for this charger
                    retry_config = self.get_retry_config(pending_msg.charger_id)
                    max_retries = retry_config["max_retries"]
                    retry_interval = retry_config["retry_interval"]
                    retry_enabled = retry_config["retry_enabled"]
                    
                    # Check if retry is disabled for this charger
                    if not retry_enabled:
                        logger.debug(f"Retry disabled for charger {pending_msg.charger_id}, removing message {message_id}")
                        expired_messages.append(message_id)
                        continue
                    
                    # Check if message has expired (60 seconds timeout)
                    if (current_time - pending_msg.timestamp).total_seconds() > 60:
                        expired_messages.append(message_id)
                    elif pending_msg.retry_count < max_retries:
                        # Only retry if:
                        # 1. The last send attempt failed (send_successful = False), OR
                        # 2. Enough time has passed since last successful send (using retry_interval)
                        should_retry = False
                        
                        if not pending_msg.send_successful:
                            # Previous send failed, retry immediately
                            should_retry = True
                        elif pending_msg.last_send_attempt:
                            # Check if enough time has passed since last successful send
                            time_since_last_send = (current_time - pending_msg.last_send_attempt).total_seconds()
                            if time_since_last_send >= retry_interval:
                                should_retry = True
                        
                        if should_retry:
                            logger.info(f"Retrying message {message_id} ({pending_msg.action}) for {pending_msg.charger_id} (attempt {pending_msg.retry_count + 1}/{max_retries}, interval: {retry_interval}s)")
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
                        expired_msg = self.pending_messages[message_id]
                        logger.warning(f"Message {message_id} ({expired_msg.action}) expired after {expired_msg.retry_count} retries")
                        del self.pending_messages[message_id]
                        self.stats["messages_failed"] += 1
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in retry task: {e}")
    
    async def heartbeat_monitor(self):
        """Background task to monitor charger heartbeats and send heartbeat requests"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                current_time = datetime.utcnow()
                timeout_threshold = current_time - timedelta(minutes=10)  # Increased from 5 to 10 minutes
                heartbeat_request_threshold = current_time - timedelta(minutes=5)  # Request heartbeat if no heartbeat in 5 minutes
                
                # Check for chargers that haven't sent heartbeat
                db = SessionLocal()
                try:
                    stale_chargers = db.query(Charger).filter(
                        Charger.is_connected == True,
                        Charger.last_heartbeat < timeout_threshold
                    ).all()
                    
                    # Send heartbeat requests to chargers that haven't sent heartbeat recently
                    # But only if they're actually in active connections (not just marked as connected in DB)
                    chargers_needing_heartbeat = db.query(Charger).filter(
                        Charger.is_connected == True,
                        Charger.last_heartbeat < heartbeat_request_threshold
                    ).all()
                
                    for charger in chargers_needing_heartbeat:
                        if charger.id in self.charger_connections:
                            # Only send heartbeat request if charger has been connected for at least 2 minutes
                            # This prevents disconnecting newly connected chargers
                            connection_time = charger.updated_at or charger.created_at
                            if connection_time and (current_time - connection_time).total_seconds() > 120:  # 2 minutes
                                logger.info(f"Sending heartbeat request to charger {charger.id}")
                                message_id = str(uuid.uuid4())
                                heartbeat_message = [2, message_id, "GetConfiguration", {"key": ["HeartbeatInterval"]}]
                                await self.send_message_to_charger(charger.id, heartbeat_message)
                            else:
                                logger.debug(f"Skipping heartbeat request for newly connected charger {charger.id}")
                    
                    for charger in stale_chargers:
                        # Only disconnect if charger has been connected for at least 5 minutes
                        # This prevents disconnecting newly connected chargers with old heartbeat timestamps
                        connection_time = charger.updated_at or charger.created_at
                        if connection_time and (current_time - connection_time).total_seconds() > 300:  # 5 minutes
                            logger.warning(f"Charger {charger.id} heartbeat timeout (last heartbeat: {charger.last_heartbeat})")
                            charger.status = "Offline"
                            charger.is_connected = False
                            charger.updated_at = current_time
                            
                            # Remove from active connections
                            if charger.id in self.charger_connections:
                                connection_id = self.connection_ids.get(charger.id)
                                await self.remove_charger_connection(charger.id, connection_id)
                        else:
                            logger.debug(f"Skipping disconnect for newly connected charger {charger.id} with old heartbeat timestamp")
                    
                    # Also check for stale WebSocket connections that might not be in DB
                    stale_websocket_connections = []
                    for charger_id, websocket in self.charger_connections.items():
                        try:
                            # Try to ping the WebSocket to check if it's still alive
                            await asyncio.wait_for(websocket.ping(), timeout=5.0)
                            logger.debug(f"WebSocket ping successful for charger {charger_id}")
                        except asyncio.TimeoutError:
                            logger.warning(f"WebSocket ping timeout for charger {charger_id}")
                            stale_websocket_connections.append(charger_id)
                        except Exception as e:
                            logger.warning(f"WebSocket ping failed for charger {charger_id}: {e}")
                            stale_websocket_connections.append(charger_id)
                    
                    # Clean up stale WebSocket connections
                    for charger_id in stale_websocket_connections:
                        logger.warning(f"Cleaning up stale WebSocket connection for charger {charger_id}")
                        connection_id = self.connection_ids.get(charger_id)
                        await self.remove_charger_connection(charger_id, connection_id)
                    
                    if stale_chargers or stale_websocket_connections:
                        db.commit()
                        logger.info(f"Heartbeat monitor: cleaned up {len(stale_chargers)} stale chargers and {len(stale_websocket_connections)} stale WebSocket connections")
                    
                finally:
                    db.close()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
    
    async def keepalive_monitor(self):
        """Background task to keep WebSocket connections alive with periodic pings"""
        while True:
            try:
                await asyncio.sleep(120)  # Check every 2 minutes (much less frequent)
                
                if not self.charger_connections:
                    continue
                
                logger.debug(f"Checking {len(self.charger_connections)} charger connections")
                
                # Only check WebSocket connection health, don't send manual pings
                # The WebSocket server handles ping/pong automatically
                stale_connections = []
                for charger_id, websocket in self.charger_connections.items():
                    try:
                        # Just check if the connection is still open
                        if websocket.closed:
                            logger.warning(f"Charger {charger_id} WebSocket connection is closed")
                            stale_connections.append(charger_id)
                    except Exception as e:
                        logger.warning(f"Error checking charger {charger_id} connection: {e}")
                        stale_connections.append(charger_id)
                
                # Clean up stale connections
                for charger_id in stale_connections:
                    connection_id = self.connection_ids.get(charger_id)
                    await self.remove_charger_connection(charger_id, connection_id)
                
                # Note: OCPP Heartbeat requests are handled by the heartbeat_monitor task
                # This keep-alive monitor only handles WebSocket-level pings
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in keep-alive monitor: {e}")
    
    async def send_ocpp_heartbeats(self):
        """Send OCPP Heartbeat requests to chargers that haven't sent messages recently"""
        try:
            current_time = datetime.utcnow()
            heartbeat_threshold = current_time - timedelta(minutes=5)  # Send heartbeat if no message in 5 minutes (less aggressive)
            
            db = SessionLocal()
            try:
                # Find chargers that haven't sent messages recently
                chargers_needing_heartbeat = db.query(Charger).filter(
                    Charger.is_connected == True,
                    Charger.last_heartbeat < heartbeat_threshold
                ).all()
                
                for charger in chargers_needing_heartbeat:
                    if charger.id in self.charger_connections:
                        logger.debug(f"Sending OCPP Heartbeat request to charger {charger.id}")
                        message_id = str(uuid.uuid4())
                        heartbeat_message = [2, message_id, "Heartbeat", {}]
                        await self.send_message_to_charger(charger.id, heartbeat_message)
                        
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error sending OCPP heartbeats: {e}")
    
    async def send_keepalive_ping(self, charger_id: str, websocket: WebSocketServerProtocol):
        """Send a keep-alive ping to a specific charger"""
        try:
            # Send WebSocket ping frame
            await websocket.ping()
            logger.debug(f"Keep-alive ping sent to charger {charger_id}")
            
        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"Charger {charger_id} connection closed during keep-alive ping")
            # Remove the connection
            connection_id = self.connection_ids.get(charger_id)
            await self.remove_charger_connection(charger_id, connection_id)
            
        except Exception as e:
            logger.warning(f"Keep-alive ping failed for charger {charger_id}: {e}")
            # Remove the connection if ping fails
            connection_id = self.connection_ids.get(charger_id)
            await self.remove_charger_connection(charger_id, connection_id)
    
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
