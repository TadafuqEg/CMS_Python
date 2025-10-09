"""
Health and metrics endpoints
"""

from datetime import datetime, timedelta
from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.database import get_db, Charger, Session as DBSession, MessageLog
from app.services.session_manager import SessionManager

router = APIRouter()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Check system health and return status information"""
    
    # Get connected chargers count
    connected_chargers = db.query(Charger).filter(Charger.is_connected == True).count()
    total_chargers = db.query(Charger).count()
    
    # Get active sessions count
    active_sessions = db.query(DBSession).filter(DBSession.status == "Active").count()
    
    # Get recent message count (last hour)
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    recent_messages = db.query(MessageLog).filter(MessageLog.timestamp >= one_hour_ago).count()
    
    # Calculate uptime (simplified - in production, track actual start time)
    uptime_hours = 24  # Placeholder
    
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "connected_chargers": connected_chargers,
        "total_chargers": total_chargers,
        "active_sessions": active_sessions,
        "recent_messages": recent_messages,
        "uptime": f"{uptime_hours}h",
        "version": "1.0.0"
    }

@router.get("/metrics")
async def get_metrics(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get Prometheus-compatible metrics"""
    
    # Connection metrics
    connected_chargers = db.query(Charger).filter(Charger.is_connected == True).count()
    total_chargers = db.query(Charger).count()
    
    # Session metrics
    active_sessions = db.query(DBSession).filter(DBSession.status == "Active").count()
    total_sessions_today = db.query(DBSession).filter(
        func.date(DBSession.created_at) == func.date(func.now())
    ).count()
    
    # Message metrics (last 24 hours)
    one_day_ago = datetime.utcnow() - timedelta(days=1)
    messages_24h = db.query(MessageLog).filter(MessageLog.timestamp >= one_day_ago).count()
    
    # Energy metrics (last 24 hours)
    energy_24h = db.query(func.sum(DBSession.energy_delivered)).filter(
        DBSession.stop_time >= one_day_ago
    ).scalar() or 0
    
    # Error metrics (last 24 hours)
    error_messages = db.query(MessageLog).filter(
        MessageLog.timestamp >= one_day_ago,
        MessageLog.status == "Error"
    ).count()
    
    return {
        "ocpp_active_connections": connected_chargers,
        "ocpp_total_chargers": total_chargers,
        "ocpp_active_sessions": active_sessions,
        "ocpp_sessions_today": total_sessions_today,
        "ocpp_messages_24h": messages_24h,
        "ocpp_energy_delivered_24h_kwh": float(energy_24h),
        "ocpp_error_messages_24h": error_messages,
        "ocpp_uptime_seconds": 86400  # Placeholder
    }

@router.get("/status")
async def get_detailed_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get detailed system status"""
    
    # Charger status breakdown
    charger_status = db.query(
        Charger.status,
        func.count(Charger.id).label('count')
    ).group_by(Charger.status).all()
    
    status_breakdown = {status: count for status, count in charger_status}
    
    # Recent activity (last 10 minutes)
    ten_minutes_ago = datetime.utcnow() - timedelta(minutes=10)
    recent_activity = db.query(MessageLog).filter(
        MessageLog.timestamp >= ten_minutes_ago
    ).order_by(MessageLog.timestamp.desc()).limit(10).all()
    
    # System configuration
    from app.models.database import SystemConfig
    configs = db.query(SystemConfig).all()
    system_config = {config.key: config.value for config in configs}
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "charger_status_breakdown": status_breakdown,
        "recent_activity": [
            {
                "timestamp": msg.timestamp.isoformat(),
                "charger_id": msg.charger_id,
                "action": msg.action,
                "type": msg.message_type,
                "status": msg.status
            }
            for msg in recent_activity
        ],
        "system_configuration": system_config,
        "database_status": "connected",
        "message_queue_status": "connected"  # Would check actual MQ status
    }
