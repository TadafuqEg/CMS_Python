"""
FastAPI OCPP Central Management System
Main application entry point with WebSocket and REST API support
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Set

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import ssl
import websockets
from websockets.server import WebSocketServerProtocol

from app.routers import health, chargers, ocpp_control, logs, internal
from app.services.ocpp_handler import OCPPHandler
from app.services.session_manager import SessionManager
from app.services.mq_bridge import MQBridge
from app.models.database import init_db
from app.core.config import settings
from app.core.security import verify_token

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

# Reduce verbosity of specific loggers
logging.getLogger('websockets').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)
logging.getLogger('uvicorn').setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# Global services
ocpp_handler = None
session_manager = None
mq_bridge = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global ocpp_handler, session_manager, mq_bridge
    
    # Startup
    logger.info("Starting OCPP Central Management System...")
    
    # Initialize database
    await init_db()
    
    # Initialize services
    session_manager = SessionManager()
    mq_bridge = MQBridge()
    ocpp_handler = OCPPHandler(session_manager, mq_bridge)
    # Attach to app.state for router access
    app.state.ocpp_handler = ocpp_handler
    
    # Start background tasks
    asyncio.create_task(mq_bridge.start())
    asyncio.create_task(ocpp_handler.start_websocket_server())
    
    logger.info("OCPP CMS started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down OCPP Central Management System...")
    if mq_bridge:
        await mq_bridge.stop()
    if ocpp_handler:
        await ocpp_handler.stop()
    logger.info("OCPP CMS shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="OCPP Central Management System",
    description="FastAPI-based OCPP 1.6/2.0.1 Central System with REST APIs",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

# Dependency for authentication
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token and return user info"""
    try:
        payload = verify_token(credentials.credentials)
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

# Include routers
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(chargers.router, prefix="/api", tags=["Chargers"])
app.include_router(ocpp_control.router, prefix="/api", tags=["OCPP Control"])
app.include_router(logs.router, prefix="/api", tags=["Logs"])
app.include_router(internal.router, prefix="/api", tags=["Internal"])

# WebSocket endpoint for OCPP chargers
@app.websocket("/ocpp/{charger_id}")
async def websocket_ocpp_endpoint(websocket: WebSocket, charger_id: str):
    """WebSocket endpoint for OCPP charger connections"""
    try:
        if not ocpp_handler:
            await websocket.close(code=1011, reason="Service not ready")
            return
        
        await websocket.accept()
        await ocpp_handler.handle_charger_connection(websocket, charger_id)
    except Exception as e:
        logger.error(f"WebSocket error for charger {charger_id}: {e}")
        try:
            await websocket.close(code=1011, reason=f"Server error: {str(e)}")
        except:
            pass

# WebSocket endpoint for master connections (broadcasting)
@app.websocket("/master")
async def websocket_master_endpoint(websocket: WebSocket):
    """WebSocket endpoint for master connections (broadcasting)"""
    if not ocpp_handler:
        await websocket.close(code=1011, reason="Service not ready")
        return
    
    await ocpp_handler.handle_master_connection(websocket)

# WebSocket endpoint for real-time dashboard updates
@app.websocket("/dashboard")
async def websocket_dashboard_endpoint(websocket: WebSocket, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """WebSocket endpoint for real-time dashboard updates"""
    try:
        # Verify authentication
        payload = verify_token(credentials.credentials)
        
        if not session_manager:
            await websocket.close(code=1011, reason="Service not ready")
            return
        
        await session_manager.handle_dashboard_connection(websocket, payload)
    except Exception as e:
        logger.error(f"Dashboard WebSocket authentication failed: {e}")
        await websocket.close(code=1008, reason="Authentication failed")

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "OCPP Central Management System API",
        "version": "1.0.0",
        "docs": "/docs",
        "websocket_endpoints": {
            "chargers": "/ocpp/{charger_id}",
            "master": "/master",
            "dashboard": "/dashboard"
        }
    }

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        ssl_keyfile=settings.SSL_KEYFILE,
        ssl_certfile=settings.SSL_CERTFILE,
        log_level="info"
    )
