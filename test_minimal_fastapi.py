#!/usr/bin/env python3
"""
Minimal FastAPI test application
"""

from fastapi import FastAPI
import uvicorn

app = FastAPI(title="Test OCPP CMS", version="1.0.0")

@app.get("/")
async def root():
    return {"message": "OCPP Central Management System API", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "ok", "message": "System is healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="info")
