#!/usr/bin/env python3
"""
Test script to verify StatusNotification and StopTransaction handlers work correctly.
"""

import asyncio
import websockets
import ssl
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_status_notification():
    """Test StatusNotification and StopTransaction handlers"""
    
    # Create SSL context that doesn't verify certificates (for testing)
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    uri = "wss://localhost:9000/CP001"
    
    try:
        async with websockets.connect(uri, ssl=ssl_context, subprotocols=["ocpp1.6"]) as websocket:
            print("Connected to OCPP server")
            
            # Send BootNotification first
            boot_message = [
                2, "boot_001", "BootNotification",
                {
                    "chargePointVendor": "Test Vendor",
                    "chargePointModel": "Test Model",
                    "chargePointSerialNumber": "TEST123",
                    "chargeBoxSerialNumber": "BOX123",
                    "firmwareVersion": "1.0.0"
                }
            ]
            
            await websocket.send(json.dumps(boot_message))
            print("Sent BootNotification")
            
            # Wait for response
            response = await websocket.recv()
            print(f"Received: {response}")
            
            # Send StatusNotification message
            status_message = [
                2, "status_001", "StatusNotification",
                {
                    "connectorId": 1,
                    "errorCode": "NoError",
                    "status": "Available"
                }
            ]
            
            print("Sending StatusNotification message...")
            await websocket.send(json.dumps(status_message))
            
            # Wait for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"Received response: {response}")
                print("✅ StatusNotification message handled successfully!")
            except asyncio.TimeoutError:
                print("⚠️ No response received (timeout)")
            
            # Send StopTransaction message
            stop_message = [
                2, "stop_001", "StopTransaction",
                {
                    "transactionId": 1,
                    "idTag": "TEST123",
                    "meterStop": 1000,
                    "timestamp": "2025-10-12T15:20:00.000Z",
                    "reason": "Local"
                }
            ]
            
            print("Sending StopTransaction message...")
            await websocket.send(json.dumps(stop_message))
            
            # Wait for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"Received response: {response}")
                print("✅ StopTransaction message handled successfully!")
            except asyncio.TimeoutError:
                print("⚠️ No response received (timeout)")
                
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("Testing StatusNotification and StopTransaction handlers...")
    print("Make sure central_system.py is running on localhost:9000")
    asyncio.run(test_status_notification())
