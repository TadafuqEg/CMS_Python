#!/usr/bin/env python3
"""
FastAPI OCPP Central Management System Startup Script
"""

import os
import uvicorn
from app.main import app
from app.core.config import settings

# Override ports to avoid conflicts
os.environ["PORT"] = "8001"
os.environ["OCPP_WEBSOCKET_PORT"] = "9001"

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )
