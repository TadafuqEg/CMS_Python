#!/usr/bin/env python3
"""
FastAPI OCPP Central Management System Startup Script
"""

import os
import uvicorn
from app.main import app
from app.core.config import settings, get_uvicorn_ssl_kwargs

# Override ports to avoid conflicts
os.environ["PORT"] = "8001"
os.environ["OCPP_WEBSOCKET_PORT"] = "1025"

if __name__ == "__main__":
    # Get SSL certificate files if available
    ssl_kwargs = get_uvicorn_ssl_kwargs()
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info",
        **ssl_kwargs
    )
