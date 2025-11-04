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

from app.routers import health, chargers, ocpp_control, logs, internal, rfid_cards, users
from app.services.ocpp_handler import OCPPHandler
from app.services.session_manager import SessionManager
from app.services.mq_bridge import MQBridge
from app.models.database import init_db
from app.core.config import settings, create_ssl_context, get_uvicorn_ssl_kwargs
from app.core.security import verify_token

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logging.getLogger('websockets').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)
logging.getLogger('uvicorn').setLevel(logging.INFO)
logging.getLogger('watchfiles').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

ocpp_handler = None
session_manager = None
mq_bridge = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global ocpp_handler, session_manager, mq_bridge
    logger.info("Starting OCPP Central Management System...")
    await init_db()
    session_manager = SessionManager()
    mq_bridge = MQBridge()
    ocpp_handler = OCPPHandler(session_manager, mq_bridge)
    app.state.ocpp_handler = ocpp_handler
    asyncio.create_task(mq_bridge.start())
    asyncio.create_task(ocpp_handler.start_websocket_server())
    asyncio.create_task(session_manager.start())  # Added to start SessionManager
    logger.info("OCPP CMS started successfully")
    yield
    logger.info("Shutting down OCPP Central Management System...")
    if mq_bridge:
        await mq_bridge.stop()
    if ocpp_handler:
        await ocpp_handler.stop()
    if session_manager:
        await session_manager.stop()
    logger.info("OCPP CMS shutdown complete")

app = FastAPI(
    title="OCPP Central Management System",
    description="FastAPI-based OCPP 1.6/2.0.1 Central System with REST APIs",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = verify_token(credentials.credentials)
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(chargers.router, prefix="/api", tags=["Chargers"])
app.include_router(ocpp_control.router, prefix="/api", tags=["OCPP Control"])
app.include_router(logs.router, prefix="/api", tags=["Logs"])
app.include_router(internal.router, prefix="/api", tags=["Internal"])
app.include_router(rfid_cards.router, prefix="/api", tags=["RFID Cards"])
app.include_router(users.router, prefix="/api", tags=["Users"])

@app.websocket("/ocpp/{charger_id}")
async def websocket_ocpp_endpoint(websocket: WebSocket, charger_id: str):
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

@app.websocket("/master")
async def websocket_master_endpoint(websocket: WebSocket):
    if not ocpp_handler:
        await websocket.close(code=1011, reason="Service not ready")
        return
    await ocpp_handler.handle_master_connection(websocket)

@app.websocket("/dashboard")
async def websocket_dashboard_endpoint(websocket: WebSocket, credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
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
    import os
    host = os.getenv("HOST", settings.HOST)
    port = int(os.getenv("PORT", settings.PORT))
    ws_port = int(os.getenv("OCPP_WEBSOCKET_PORT", settings.OCPP_WEBSOCKET_PORT))
    reload = os.getenv("DEBUG", str(settings.DEBUG)).lower() == "true"
    
    # Get SSL certificate files if available
    ssl_kwargs = get_uvicorn_ssl_kwargs()
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
        **ssl_kwargs
    )