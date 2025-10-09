"""
Simple Message Queue Bridge without Redis dependency
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, asdict

import aiohttp
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
    """Simple Message Queue Bridge without Redis dependency"""
    
    def __init__(self):
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
            
            logger.info("Simple Message Queue Bridge started (without Redis)")
            
        except Exception as e:
            logger.error(f"Failed to start MQ Bridge: {e}")
            # Don't raise exception, just log the error
            logger.warning("MQ Bridge will run in limited mode without Redis")
    
    async def stop(self):
        """Stop the message queue bridge"""
        logger.info("Stopping Simple Message Queue Bridge...")
        
        # Cancel background tasks
        if self.message_processor_task:
            self.message_processor_task.cancel()
        if self.health_check_task:
            self.health_check_task.cancel()
        
        # Close connections
        if self.http_session:
            await self.http_session.close()
        
        logger.info("Simple Message Queue Bridge stopped")
    
    async def send_event(self, event_type: str, charger_id: str, data: Dict[str, Any]):
        """Send event to Laravel CMS"""
        try:
            event = EventMessage(
                event_type=event_type,
                charger_id=charger_id,
                data=data,
                timestamp=datetime.utcnow()
            )
            
            # Try HTTP only
            success = await self.send_via_http(event)
            
            if success:
                self.stats["events_sent"] += 1
            else:
                self.stats["events_failed"] += 1
                logger.warning(f"Failed to send event {event_type} for {charger_id}")
            
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
    
    async def message_processor(self):
        """Background task to process messages"""
        while True:
            try:
                # Simple message processing without Redis
                await asyncio.sleep(1)  # Small delay
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in message processor: {e}")
                await asyncio.sleep(1)
    
    async def health_check(self):
        """Background task to check system health"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                # Check HTTP connection to Laravel
                if self.http_session:
                    try:
                        async with self.http_session.get(f"{settings.LARAVEL_API_URL}/health") as response:
                            if response.status != 200:
                                logger.warning(f"Laravel health check failed with status {response.status}")
                    except Exception as e:
                        logger.warning(f"Laravel health check failed: {e}")
                
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
            "redis_connected": False,
            "http_session_active": self.http_session is not None,
            "statistics": self.stats,
            "mode": "simple"
        }
