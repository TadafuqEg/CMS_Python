"""
Logging and diagnostics endpoints
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from pydantic import BaseModel

from app.models.database import get_db, MessageLog, Charger

router = APIRouter()

# Pydantic models
class LogEntry(BaseModel):
    timestamp: datetime
    charger_id: str
    type: str  # IN, OUT
    action: str
    message_id: Optional[str]
    status: str
    processing_time: Optional[float]

class DiagnosticsRequest(BaseModel):
    charger_id: str
    location: str
    retries: Optional[int] = 3
    retry_interval: Optional[int] = 5

@router.get("/logs", response_model=List[LogEntry])
async def get_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    charger_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    message_type: Optional[str] = Query(None, description="IN or OUT"),
    status: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """Retrieve recent system logs for debugging or monitoring"""
    
    query = db.query(MessageLog)
    
    # Apply filters
    if charger_id:
        query = query.filter(MessageLog.charger_id == charger_id)
    if action:
        query = query.filter(MessageLog.action == action)
    if message_type:
        query = query.filter(MessageLog.message_type == message_type)
    if status:
        query = query.filter(MessageLog.status == status)
    if start_time:
        query = query.filter(MessageLog.timestamp >= start_time)
    if end_time:
        query = query.filter(MessageLog.timestamp <= end_time)
    
    # Default to last 24 hours if no time range specified
    if not start_time and not end_time:
        default_start = datetime.utcnow() - timedelta(hours=24)
        query = query.filter(MessageLog.timestamp >= default_start)
    
    # Apply pagination and ordering
    logs = query.order_by(desc(MessageLog.timestamp)).offset(skip).limit(limit).all()
    
    return [
        LogEntry(
            timestamp=log.timestamp,
            charger_id=log.charger_id,
            type=log.message_type,
            action=log.action,
            message_id=log.message_id,
            status=log.status,
            processing_time=log.processing_time
        )
        for log in logs
    ]

@router.get("/logs/summary")
async def get_logs_summary(
    hours: int = Query(24, ge=1, le=168),  # Default 24 hours, max 1 week
    charger_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get summary statistics of logs"""
    
    # Calculate time range
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)
    
    query = db.query(MessageLog).filter(MessageLog.timestamp >= start_time)
    
    if charger_id:
        query = query.filter(MessageLog.charger_id == charger_id)
    
    logs = query.all()
    
    # Calculate statistics
    total_messages = len(logs)
    in_messages = len([log for log in logs if log.message_type == "IN"])
    out_messages = len([log for log in logs if log.message_type == "OUT"])
    error_messages = len([log for log in logs if log.status == "Error"])
    
    # Action breakdown
    action_counts = {}
    for log in logs:
        action_counts[log.action] = action_counts.get(log.action, 0) + 1
    
    # Charger breakdown
    charger_counts = {}
    for log in logs:
        charger_counts[log.charger_id] = charger_counts.get(log.charger_id, 0) + 1
    
    # Average processing time
    processing_times = [log.processing_time for log in logs if log.processing_time is not None]
    avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
    
    return {
        "period_hours": hours,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "total_messages": total_messages,
        "in_messages": in_messages,
        "out_messages": out_messages,
        "error_messages": error_messages,
        "error_rate": (error_messages / total_messages * 100) if total_messages > 0 else 0,
        "average_processing_time_ms": round(avg_processing_time, 2),
        "action_breakdown": action_counts,
        "charger_breakdown": charger_counts
    }

@router.get("/logs/{charger_id}/recent")
async def get_charger_recent_logs(
    charger_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get recent logs for a specific charger"""
    
    # Verify charger exists
    charger = db.query(Charger).filter(Charger.id == charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    logs = db.query(MessageLog).filter(
        MessageLog.charger_id == charger_id
    ).order_by(desc(MessageLog.timestamp)).limit(limit).all()
    
    return [
        {
            "timestamp": log.timestamp.isoformat(),
            "type": log.message_type,
            "action": log.action,
            "message_id": log.message_id,
            "status": log.status,
            "processing_time": log.processing_time,
            "request": log.request[:200] + "..." if log.request and len(log.request) > 200 else log.request,
            "response": log.response[:200] + "..." if log.response and len(log.response) > 200 else log.response
        }
        for log in logs
    ]

@router.post("/diagnostics/upload")
async def request_diagnostics_upload(
    request: DiagnosticsRequest,
    db: Session = Depends(get_db)
):
    """Request a charger to upload diagnostic logs"""
    
    # Verify charger exists and is connected
    charger = db.query(Charger).filter(Charger.id == request.charger_id).first()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    if not charger.is_connected:
        raise HTTPException(status_code=400, detail="Charger is not connected")
    
    # TODO: Send GetDiagnostics OCPP command via WebSocket
    # This would require access to the OCPP handler
    
    return {
        "status": "Accepted",
        "message": "Diagnostics upload request sent successfully",
        "charger_id": request.charger_id,
        "location": request.location,
        "retries": request.retries,
        "retry_interval": request.retry_interval
    }

@router.get("/diagnostics/status")
async def get_diagnostics_status(
    charger_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get status of diagnostic uploads"""
    
    # TODO: Implement diagnostics status tracking
    # This would require a diagnostics status table
    
    return {
        "message": "Diagnostics status endpoint not yet implemented",
        "charger_id": charger_id,
        "pending_uploads": [],
        "completed_uploads": []
    }

@router.get("/logs/export")
async def export_logs(
    format: str = Query("json", regex="^(json|csv)$"),
    charger_id: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: int = Query(10000, ge=1, le=100000),
    db: Session = Depends(get_db)
):
    """Export logs in JSON or CSV format"""
    
    query = db.query(MessageLog)
    
    # Apply filters
    if charger_id:
        query = query.filter(MessageLog.charger_id == charger_id)
    if start_time:
        query = query.filter(MessageLog.timestamp >= start_time)
    if end_time:
        query = query.filter(MessageLog.timestamp <= end_time)
    
    # Default to last 7 days if no time range specified
    if not start_time and not end_time:
        default_start = datetime.utcnow() - timedelta(days=7)
        query = query.filter(MessageLog.timestamp >= default_start)
    
    logs = query.order_by(desc(MessageLog.timestamp)).limit(limit).all()
    
    if format == "csv":
        # Generate CSV content
        import io
        import csv
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            "timestamp", "charger_id", "message_type", "action", "message_id",
            "status", "processing_time", "request", "response"
        ])
        
        # Write data
        for log in logs:
            writer.writerow([
                log.timestamp.isoformat(),
                log.charger_id,
                log.message_type,
                log.action,
                log.message_id,
                log.status,
                log.processing_time,
                log.request,
                log.response
            ])
        
        content = output.getvalue()
        output.close()
        
        return {
            "format": "csv",
            "content": content,
            "record_count": len(logs),
            "filename": f"ocpp_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    
    else:  # JSON format
        return {
            "format": "json",
            "logs": [
                {
                    "timestamp": log.timestamp.isoformat(),
                    "charger_id": log.charger_id,
                    "message_type": log.message_type,
                    "action": log.action,
                    "message_id": log.message_id,
                    "status": log.status,
                    "processing_time": log.processing_time,
                    "request": log.request,
                    "response": log.response
                }
                for log in logs
            ],
            "record_count": len(logs)
        }

@router.delete("/logs/cleanup")
async def cleanup_old_logs(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """Clean up old log entries"""
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Count logs to be deleted
    logs_to_delete = db.query(MessageLog).filter(MessageLog.timestamp < cutoff_date).count()
    
    # Delete old logs
    db.query(MessageLog).filter(MessageLog.timestamp < cutoff_date).delete()
    db.commit()
    
    return {
        "message": f"Cleaned up {logs_to_delete} log entries older than {days} days",
        "deleted_count": logs_to_delete,
        "cutoff_date": cutoff_date.isoformat()
    }
