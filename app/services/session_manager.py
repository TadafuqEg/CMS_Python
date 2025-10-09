"""
Session management service for tracking charging sessions and real-time status
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Set, Optional, Any, List
from dataclasses import dataclass, asdict

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.models.database import SessionLocal, Charger, Connector, Session as DBSession
from app.core.config import settings

logger = logging.getLogger(__name__)

@dataclass
class SessionStatus:
    """Real-time session status"""
    session_id: int
    transaction_id: Optional[int]
    charger_id: str
    connector_id: Optional[int]
    id_tag: Optional[str]
    user_id: Optional[str]
    start_time: datetime
    stop_time: Optional[datetime]
    duration: Optional[int]
    energy_delivered: float
    cost: float
    status: str
    meter_start: Optional[float]
    meter_stop: Optional[float]
    power_delivered: float
    current_voltage: Optional[float]
    current_amperage: Optional[float]

@dataclass
class ChargerStatus:
    """Real-time charger status"""
    charger_id: str
    status: str
    is_connected: bool
    last_heartbeat: Optional[datetime]
    connectors: List[Dict[str, Any]]
    active_sessions: int
    total_energy_today: float
    total_sessions_today: int

class SessionManager:
    """Manages charging sessions and real-time status updates"""
    
    def __init__(self):
        self.active_sessions: Dict[int, SessionStatus] = {}
        self.charger_status: Dict[str, ChargerStatus] = {}
        self.dashboard_connections: Set[WebSocket] = set()
        
        # Background tasks
        self.status_update_task = None
        self.session_cleanup_task = None
        
        # Statistics
        self.stats = {
            "total_sessions": 0,
            "active_sessions": 0,
            "completed_sessions": 0,
            "total_energy_delivered": 0.0,
            "total_revenue": 0.0
        }
    
    async def start(self):
        """Start session manager background tasks"""
        self.status_update_task = asyncio.create_task(self.status_updater())
        self.session_cleanup_task = asyncio.create_task(self.session_cleanup())
        logger.info("Session manager started")
    
    async def stop(self):
        """Stop session manager"""
        if self.status_update_task:
            self.status_update_task.cancel()
        if self.session_cleanup_task:
            self.session_cleanup_task.cancel()
        logger.info("Session manager stopped")
    
    async def handle_ocpp_message(self, charger_id: str, action: str, payload: Dict[str, Any], response: Optional[Dict[str, Any]]):
        """Handle OCPP messages and update session status"""
        try:
            if action == "StartTransaction":
                await self.handle_start_transaction(charger_id, payload, response)
            elif action == "StopTransaction":
                await self.handle_stop_transaction(charger_id, payload, response)
            elif action == "MeterValues":
                await self.handle_meter_values(charger_id, payload)
            elif action == "StatusNotification":
                await self.handle_status_notification(charger_id, payload)
            elif action == "Heartbeat":
                await self.handle_heartbeat(charger_id, payload)
            elif action == "BootNotification":
                await self.handle_boot_notification(charger_id, payload)
        except Exception as e:
            logger.error(f"Error handling OCPP message {action} from {charger_id}: {e}")
    
    async def handle_start_transaction(self, charger_id: str, payload: Dict[str, Any], response: Optional[Dict[str, Any]]):
        """Handle start transaction"""
        if not response:
            return
        
        transaction_id = response.get("transactionId")
        connector_id = payload.get("connectorId", 0)
        id_tag = payload.get("idTag")
        meter_start = payload.get("meterStart", 0)
        
        # Get session from database
        db = SessionLocal()
        try:
            session = db.query(DBSession).filter(
                DBSession.charger_id == charger_id,
                DBSession.transaction_id == transaction_id
            ).first()
            
            if session:
                # Create session status
                session_status = SessionStatus(
                    session_id=session.id,
                    transaction_id=transaction_id,
                    charger_id=charger_id,
                    connector_id=connector_id,
                    id_tag=id_tag,
                    user_id=session.user_id,
                    start_time=session.start_time,
                    stop_time=None,
                    duration=None,
                    energy_delivered=0.0,
                    cost=0.0,
                    status="Active",
                    meter_start=meter_start,
                    meter_stop=None,
                    power_delivered=0.0,
                    current_voltage=None,
                    current_amperage=None
                )
                
                self.active_sessions[session.id] = session_status
                self.stats["active_sessions"] += 1
                
                # Update charger status
                await self.update_charger_status(charger_id)
                
                # Notify dashboard
                await self.notify_dashboard("session_started", asdict(session_status))
                
        finally:
            db.close()
    
    async def handle_stop_transaction(self, charger_id: str, payload: Dict[str, Any], response: Optional[Dict[str, Any]]):
        """Handle stop transaction"""
        transaction_id = payload.get("transactionId")
        meter_stop = payload.get("meterStop", 0)
        
        # Find active session
        session_status = None
        for session in self.active_sessions.values():
            if session.transaction_id == transaction_id and session.charger_id == charger_id:
                session_status = session
                break
        
        if session_status:
            # Update session status
            session_status.stop_time = datetime.utcnow()
            session_status.duration = int((session_status.stop_time - session_status.start_time).total_seconds())
            session_status.meter_stop = meter_stop
            session_status.energy_delivered = (meter_stop - session_status.meter_start) / 1000  # Convert Wh to kWh
            session_status.status = "Completed"
            
            # Calculate cost (simplified - would use tariff in real implementation)
            session_status.cost = session_status.energy_delivered * 0.15  # $0.15 per kWh
            
            # Update statistics
            self.stats["completed_sessions"] += 1
            self.stats["total_energy_delivered"] += session_status.energy_delivered
            self.stats["total_revenue"] += session_status.cost
            
            # Remove from active sessions
            del self.active_sessions[session_status.session_id]
            self.stats["active_sessions"] -= 1
            
            # Update charger status
            await self.update_charger_status(charger_id)
            
            # Notify dashboard
            await self.notify_dashboard("session_stopped", asdict(session_status))
    
    async def handle_meter_values(self, charger_id: str, payload: Dict[str, Any]):
        """Handle meter values"""
        transaction_id = payload.get("transactionId")
        meter_value = payload.get("meterValue", [])
        
        if not transaction_id or not meter_value:
            return
        
        # Find active session
        session_status = None
        for session in self.active_sessions.values():
            if session.transaction_id == transaction_id and session.charger_id == charger_id:
                session_status = session
                break
        
        if session_status:
            # Update session with latest meter readings
            for mv in meter_value:
                for sample in mv.get("sampledValue", []):
                    measurand = sample.get("measurand")
                    value = float(sample.get("value", 0))
                    
                    if measurand == "Energy.Active.Import.Register":
                        session_status.energy_delivered = value / 1000  # Convert Wh to kWh
                    elif measurand == "Power.Active.Import":
                        session_status.power_delivered = value / 1000  # Convert W to kW
                    elif measurand == "Voltage":
                        session_status.current_voltage = value
                    elif measurand == "Current.Import":
                        session_status.current_amperage = value
            
            # Notify dashboard of meter update
            await self.notify_dashboard("meter_update", asdict(session_status))
    
    async def handle_status_notification(self, charger_id: str, payload: Dict[str, Any]):
        """Handle status notification"""
        connector_id = payload.get("connectorId", 0)
        status = payload.get("status")
        error_code = payload.get("errorCode")
        
        # Update charger status
        await self.update_charger_status(charger_id)
        
        # Notify dashboard
        await self.notify_dashboard("status_update", {
            "charger_id": charger_id,
            "connector_id": connector_id,
            "status": status,
            "error_code": error_code
        })
    
    async def handle_heartbeat(self, charger_id: str, payload: Dict[str, Any]):
        """Handle heartbeat"""
        # Update charger last heartbeat
        if charger_id in self.charger_status:
            self.charger_status[charger_id].last_heartbeat = datetime.utcnow()
    
    async def handle_boot_notification(self, charger_id: str, payload: Dict[str, Any]):
        """Handle boot notification"""
        # Initialize charger status
        await self.update_charger_status(charger_id)
    
    async def update_charger_status(self, charger_id: str):
        """Update charger status from database"""
        db = SessionLocal()
        try:
            charger = db.query(Charger).filter(Charger.id == charger_id).first()
            if not charger:
                return
            
            # Get connectors
            connectors = db.query(Connector).filter(Connector.charger_id == charger_id).all()
            connector_data = [
                {
                    "id": conn.id,
                    "connector_id": conn.connector_id,
                    "status": conn.status,
                    "error_code": conn.error_code,
                    "energy_delivered": conn.energy_delivered,
                    "power_delivered": conn.power_delivered
                }
                for conn in connectors
            ]
            
            # Count active sessions
            active_sessions = len([s for s in self.active_sessions.values() if s.charger_id == charger_id])
            
            # Calculate today's statistics
            today = datetime.utcnow().date()
            today_sessions = db.query(DBSession).filter(
                DBSession.charger_id == charger_id,
                func.date(DBSession.start_time) == today
            ).all()
            
            total_energy_today = sum(s.energy_delivered or 0 for s in today_sessions)
            total_sessions_today = len(today_sessions)
            
            # Update charger status
            self.charger_status[charger_id] = ChargerStatus(
                charger_id=charger_id,
                status=charger.status,
                is_connected=charger.is_connected,
                last_heartbeat=charger.last_heartbeat,
                connectors=connector_data,
                active_sessions=active_sessions,
                total_energy_today=total_energy_today,
                total_sessions_today=total_sessions_today
            )
            
        finally:
            db.close()
    
    async def handle_dashboard_connection(self, websocket: WebSocket, user_payload: Dict[str, Any]):
        """Handle dashboard WebSocket connection"""
        self.dashboard_connections.add(websocket)
        logger.info(f"Dashboard connection established. Total connections: {len(self.dashboard_connections)}")
        
        try:
            # Send initial data
            await self.send_initial_data(websocket, user_payload)
            
            # Keep connection alive
            async for message in websocket:
                # Handle dashboard messages if needed
                pass
                
        except Exception as e:
            logger.error(f"Dashboard connection error: {e}")
        finally:
            self.dashboard_connections.discard(websocket)
            logger.info(f"Dashboard connection closed. Total connections: {len(self.dashboard_connections)}")
    
    async def send_initial_data(self, websocket: WebSocket, user_payload: Dict[str, Any]):
        """Send initial data to dashboard connection"""
        try:
            # Send current status
            initial_data = {
                "type": "initial_data",
                "timestamp": datetime.utcnow().isoformat(),
                "active_sessions": [asdict(session) for session in self.active_sessions.values()],
                "charger_status": {k: asdict(v) for k, v in self.charger_status.items()},
                "statistics": self.stats
            }
            
            await websocket.send_text(json.dumps(initial_data))
            
        except Exception as e:
            logger.error(f"Error sending initial data: {e}")
    
    async def notify_dashboard(self, event_type: str, data: Dict[str, Any]):
        """Notify all dashboard connections of an event"""
        if not self.dashboard_connections:
            return
        
        message = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data
        }
        
        message_text = json.dumps(message)
        disconnected = set()
        
        for websocket in self.dashboard_connections:
            try:
                await websocket.send_text(message_text)
            except Exception as e:
                logger.error(f"Error sending dashboard notification: {e}")
                disconnected.add(websocket)
        
        # Remove disconnected websockets
        for websocket in disconnected:
            self.dashboard_connections.discard(websocket)
    
    async def status_updater(self):
        """Background task to update status periodically"""
        while True:
            try:
                await asyncio.sleep(30)  # Update every 30 seconds
                
                # Update all charger statuses
                for charger_id in list(self.charger_status.keys()):
                    await self.update_charger_status(charger_id)
                
                # Send status update to dashboard
                if self.dashboard_connections:
                    await self.notify_dashboard("status_update", {
                        "charger_status": {k: asdict(v) for k, v in self.charger_status.items()},
                        "active_sessions": [asdict(session) for session in self.active_sessions.values()],
                        "statistics": self.stats
                    })
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in status updater: {e}")
    
    async def session_cleanup(self):
        """Background task to cleanup old sessions"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                # Clean up old completed sessions from memory
                current_time = datetime.utcnow()
                old_sessions = []
                
                for session_id, session in self.active_sessions.items():
                    # Remove sessions that have been inactive for more than 24 hours
                    if (current_time - session.start_time).total_seconds() > 86400:
                        old_sessions.append(session_id)
                
                for session_id in old_sessions:
                    if session_id in self.active_sessions:
                        del self.active_sessions[session_id]
                        self.stats["active_sessions"] -= 1
                
                if old_sessions:
                    logger.info(f"Cleaned up {len(old_sessions)} old sessions")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in session cleanup: {e}")
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all active sessions"""
        return [asdict(session) for session in self.active_sessions.values()]
    
    def get_charger_status(self, charger_id: str) -> Optional[Dict[str, Any]]:
        """Get status for specific charger"""
        if charger_id in self.charger_status:
            return asdict(self.charger_status[charger_id])
        return None
    
    def get_all_charger_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status for all chargers"""
        return {k: asdict(v) for k, v in self.charger_status.items()}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get session statistics"""
        return self.stats.copy()
