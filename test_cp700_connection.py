#!/usr/bin/env python3
"""
Simple test script to simulate CP700 charger connection for retry mechanism testing
"""

import asyncio
import json
import websockets
import requests
import time
import ssl
from datetime import datetime

# Test configuration
WEBSOCKET_URL = "ws://localhost:9001"  # Correct WebSocket port
FASTAPI_URL = "http://localhost:8001"   # Correct FastAPI port
CHARGER_ID = "CP700"

async def simulate_cp700_connection():
    """Simulate CP700 charger connection"""
    
    print("🔌 Simulating CP700 Charger Connection")
    print("=" * 50)
    
    # Step 1: Connect to WebSocket
    print(f"\n1️⃣ Connecting to WebSocket: {WEBSOCKET_URL}/{CHARGER_ID}")
    try:
        async with websockets.connect(f"{WEBSOCKET_URL}/{CHARGER_ID}") as websocket:
            print(f"   ✅ WebSocket connected successfully")
            
            # Wait a moment for the connection to be processed
            await asyncio.sleep(1)
            
            # Step 2: Send BootNotification
            print(f"\n2️⃣ Sending BootNotification...")
            boot_notification = [
                2,  # MessageType: CALL
                "boot-msg-001",  # MessageId
                "BootNotification",  # Action
                {
                    "chargePointVendor": "CP700Vendor",
                    "chargePointModel": "CP700Model",
                    "chargePointSerialNumber": "CP700-SERIAL-001",
                    "firmwareVersion": "1.0.0"
                }
            ]
            
            await websocket.send(json.dumps(boot_notification))
            print(f"   ✅ BootNotification sent")
            
            # Wait for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                response_data = json.loads(response)
                print(f"   📨 BootNotification response: {response_data}")
            except asyncio.TimeoutError:
                print(f"   ⏰ Timeout waiting for BootNotification response")
            except Exception as e:
                print(f"   ❌ Error receiving BootNotification response: {e}")
            
            # Step 3: Keep connection alive for a while to test retry mechanism
            print(f"\n3️⃣ Keeping connection alive for 30 seconds to test retry mechanism...")
            await asyncio.sleep(30)
            
            print(f"\n✅ CP700 simulation completed")
            
    except Exception as e:
        print(f"   ❌ WebSocket connection failed: {e}")

async def main():
    """Main test function"""
    print("🚀 Starting CP700 Connection Simulation")
    print("=" * 50)
    
    # Simulate CP700 connection
    await simulate_cp700_connection()
    
    print(f"\n🎉 Test completed!")
    print(f"   📝 Check the logs for retry mechanism debug output")
    print(f"   🔍 Verify retry_count increments properly")

if __name__ == "__main__":
    asyncio.run(main())
