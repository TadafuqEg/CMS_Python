"""
Message Queue Bridge for Laravel CMS integration
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, asdict

import aiohttp
import redis.asyncio as redis
from app.core.config import settings

logger = logging.getLogger(__name__)

@dataclass
class EventMessage:
    """Event message for Laravel CMS"""
    event_type: str
    charger_id: str
    data: Dict[str, Any]
    timestamp: datetime
    source: str = "ocpp_service"

class MQBridge:
    """Message Queue Bridge for Laravel CMS integration"""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.http_session: Optional[aiohttp.ClientSession] = None
        
        # Event handlers
        self.event_handlers: Dict[str, Callable] = {}
        
        # Background tasks
        self.message_processor_task = None
        self.health_check_task = None
        
        # Statistics
        self.stats = {
            "events_sent": 0,
            "events_failed": 0,
            "http_requests": 0,
            "http_errors": 0,
            "queue_size": 0
        }
    
    async def start(self):
        """Start the message queue bridge"""
        try:
            # Initialize Redis connection
            self.redis_client = redis.from_url(settings.REDIS_URL)
            await self.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            logger.info("MQ Bridge will run without Redis (HTTP-only mode)")
            self.redis_client = None
        
        try:
            # Initialize HTTP session
            self.http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    "Authorization": f"Bearer {settings.LARAVEL_API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            
            # Start background tasks
            self.message_processor_task = asyncio.create_task(self.message_processor())
            self.health_check_task = asyncio.create_task(self.health_check())
            
            logger.info("Message Queue Bridge started")
            
        except Exception as e:
            logger.error(f"Failed to start MQ Bridge: {e}")
            # Don't raise exception, just log the error
            logger.warning("MQ Bridge will run in limited mode")
    
    async def stop(self):
        """Stop the message queue bridge"""
        logger.info("Stopping Message Queue Bridge...")
        
        # Cancel background tasks
        if self.message_processor_task:
            self.message_processor_task.cancel()
        if self.health_check_task:
            self.health_check_task.cancel()
        
        # Close connections
        if self.redis_client:
            await self.redis_client.close()
        
        if self.http_session:
            await self.http_session.close()
        
        logger.info("Message Queue Bridge stopped")
    
    async def send_event(self, event_type: str, charger_id: str, data: Dict[str, Any]):
        """Send event to Laravel CMS"""
        try:
            event = EventMessage(
                event_type=event_type,
                charger_id=charger_id,
                data=data,
                timestamp=datetime.utcnow()
            )
            
            # Try HTTP first, fallback to Redis queue
            success = await self.send_via_http(event)
            
            if not success:
                await self.send_via_redis(event)
            
            self.stats["events_sent"] += 1
            
        except Exception as e:
            logger.error(f"Failed to send event {event_type} for {charger_id}: {e}")
            self.stats["events_failed"] += 1
    
    async def send_via_http(self, event: EventMessage) -> bool:
        """Send event via HTTP to Laravel CMS"""
        try:
            url = f"{settings.LARAVEL_API_URL}/ocpp/events"
            payload = asdict(event)
            payload["timestamp"] = event.timestamp.isoformat()
            
            async with self.http_session.post(url, json=payload) as response:
                self.stats["http_requests"] += 1
                
                if response.status == 200:
                    logger.debug(f"Event sent via HTTP: {event.event_type}")
                    return True
                else:
                    logger.warning(f"HTTP request failed with status {response.status}")
                    self.stats["http_errors"] += 1
                    return False
                    
        except Exception as e:
            logger.error(f"HTTP request failed: {e}")
            self.stats["http_errors"] += 1
            return False
    
    async def send_via_redis(self, event: EventMessage):
        """Send event via Redis queue"""
        if not self.redis_client:
            logger.warning("Redis not available, skipping Redis queue")
            return
            
        try:
            queue_name = f"{settings.MQ_EXCHANGE}:events"
            payload = asdict(event)
            payload["timestamp"] = event.timestamp.isoformat()
            
            await self.redis_client.lpush(queue_name, json.dumps(payload))
            logger.debug(f"Event queued via Redis: {event.event_type}")
            
        except Exception as e:
            logger.error(f"Redis queue failed: {e}")
            # Don't raise exception, just log the error
    
    async def send_boot_notification(self, charger_id: str, charger_data: Dict[str, Any]):
        """Send boot notification event"""
        await self.send_event("boot_notification", charger_id, {
            "vendor": charger_data.get("vendor"),
            "model": charger_data.get("model"),
            "serial_number": charger_data.get("serial_number"),
            "firmware_version": charger_data.get("firmware_version")
        })
    
    async def send_transaction_start(self, charger_id: str, session_data: Dict[str, Any]):
        """Send transaction start event"""
        await self.send_event("transaction_start", charger_id, {
            "transaction_id": session_data.get("transaction_id"),
            "connector_id": session_data.get("connector_id"),
            "id_tag": session_data.get("id_tag"),
            "user_id": session_data.get("user_id"),
            "start_time": session_data.get("start_time"),
            "meter_start": session_data.get("meter_start")
        })
    
    async def send_transaction_stop(self, charger_id: str, session_data: Dict[str, Any]):
        """Send transaction stop event"""
        await self.send_event("transaction_stop", charger_id, {
            "transaction_id": session_data.get("transaction_id"),
            "connector_id": session_data.get("connector_id"),
            "id_tag": session_data.get("id_tag"),
            "user_id": session_data.get("user_id"),
            "stop_time": session_data.get("stop_time"),
            "duration": session_data.get("duration"),
            "energy_delivered": session_data.get("energy_delivered"),
            "cost": session_data.get("cost"),
            "meter_stop": session_data.get("meter_stop")
        })
    
    async def send_status_notification(self, charger_id: str, status_data: Dict[str, Any]):
        """Send status notification event"""
        await self.send_event("status_notification", charger_id, {
            "connector_id": status_data.get("connector_id"),
            "status": status_data.get("status"),
            "error_code": status_data.get("error_code")
        })
    
    async def send_meter_values(self, charger_id: str, meter_data: Dict[str, Any]):
        """Send meter values event"""
        await self.send_event("meter_values", charger_id, {
            "transaction_id": meter_data.get("transaction_id"),
            "connector_id": meter_data.get("connector_id"),
            "meter_value": meter_data.get("meter_value"),
            "timestamp": meter_data.get("timestamp")
        })
    
    async def send_heartbeat(self, charger_id: str, heartbeat_data: Dict[str, Any]):
        """Send heartbeat event"""
        await self.send_event("heartbeat", charger_id, {
            "timestamp": heartbeat_data.get("timestamp"),
            "status": heartbeat_data.get("status")
        })
    
    async def send_fault_notification(self, charger_id: str, fault_data: Dict[str, Any]):
        """Send fault notification event"""
        await self.send_event("fault_notification", charger_id, {
            "connector_id": fault_data.get("connector_id"),
            "error_code": fault_data.get("error_code"),
            "info": fault_data.get("info"),
            "timestamp": fault_data.get("timestamp")
        })
    
    async def send_remote_command_result(self, charger_id: str, command_data: Dict[str, Any]):
        """Send remote command result event"""
        await self.send_event("remote_command_result", charger_id, {
            "command": command_data.get("command"),
            "message_id": command_data.get("message_id"),
            "status": command_data.get("status"),
            "response": command_data.get("response"),
            "timestamp": command_data.get("timestamp")
        })
    
    async def receive_command(self, command_data: Dict[str, Any]) -> Dict[str, Any]:
        """Receive command from Laravel CMS"""
        try:
            command_type = command_data.get("command")
            charger_id = command_data.get("charger_id")
            payload = command_data.get("payload", {})
            
            # Process command based on type
            if command_type == "RemoteStartTransaction":
                return await self.process_remote_start(charger_id, payload)
            elif command_type == "RemoteStopTransaction":
                return await self.process_remote_stop(charger_id, payload)
            elif command_type == "UnlockConnector":
                return await self.process_unlock_connector(charger_id, payload)
            elif command_type == "Reset":
                return await self.process_reset(charger_id, payload)
            elif command_type == "ChangeConfiguration":
                return await self.process_change_configuration(charger_id, payload)
            else:
                return {"status": "error", "message": f"Unknown command: {command_type}"}
                
        except Exception as e:
            logger.error(f"Error processing command: {e}")
            return {"status": "error", "message": str(e)}
    
    async def process_remote_start(self, charger_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process remote start command"""
        # TODO: Implement actual remote start processing
        # This would integrate with the OCPP handler
        return {"status": "accepted", "message": "Remote start command processed"}
    
    async def process_remote_stop(self, charger_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process remote stop command"""
        # TODO: Implement actual remote stop processing
        return {"status": "accepted", "message": "Remote stop command processed"}
    
    async def process_unlock_connector(self, charger_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process unlock connector command"""
        # TODO: Implement actual unlock processing
        return {"status": "accepted", "message": "Unlock connector command processed"}
    
    async def process_reset(self, charger_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process reset command"""
        # TODO: Implement actual reset processing
        return {"status": "accepted", "message": "Reset command processed"}
    
    async def process_change_configuration(self, charger_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process change configuration command"""
        # TODO: Implement actual configuration change processing
        return {"status": "accepted", "message": "Change configuration command processed"}
    
    async def message_processor(self):
        """Background task to process messages from Redis queue"""
        while True:
            try:
                if self.redis_client:
                    # Check for commands from Laravel CMS
                    queue_name = f"{settings.MQ_EXCHANGE}:commands"
                    message = await self.redis_client.brpop(queue_name, timeout=1)
                    
                    if message:
                        _, message_data = message
                        command_data = json.loads(message_data)
                        
                        # Process command
                        result = await self.receive_command(command_data)
                        
                        # Send result back if requested
                        if command_data.get("require_response"):
                            response_queue = f"{settings.MQ_EXCHANGE}:responses:{command_data.get('request_id')}"
                            await self.redis_client.lpush(response_queue, json.dumps(result))
                else:
                    # No Redis, just sleep
                    await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in message processor: {e}")
                await asyncio.sleep(1)  # Wait before retrying
    
    async def health_check(self):
        """Background task to check system health"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                # Check Redis connection
                if self.redis_client:
                    try:
                        await self.redis_client.ping()
                    except Exception as e:
                        logger.error(f"Redis health check failed: {e}")
                
                # Check HTTP connection to Laravel
                if self.http_session:
                    try:
                        async with self.http_session.get(f"{settings.LARAVEL_API_URL}/health") as response:
                            if response.status != 200:
                                logger.warning(f"Laravel health check failed with status {response.status}")
                    except Exception as e:
                        logger.warning(f"Laravel health check failed: {e}")
                
                # Update queue size
                if self.redis_client:
                    try:
                        queue_name = f"{settings.MQ_EXCHANGE}:events"
                        self.stats["queue_size"] = await self.redis_client.llen(queue_name)
                    except Exception as e:
                        logger.error(f"Failed to get queue size: {e}")
                else:
                    self.stats["queue_size"] = 0
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get bridge statistics"""
        return self.stats.copy()
    
    def get_status(self) -> Dict[str, Any]:
        """Get bridge status"""
        return {
            "redis_connected": self.redis_client is not None,
            "http_session_active": self.http_session is not None,
            "statistics": self.stats,
            "mode": "full" if self.redis_client else "http-only"
        }
