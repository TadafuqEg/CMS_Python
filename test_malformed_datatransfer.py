#!/usr/bin/env python3
"""
Test script to reproduce and verify the FormatViolationError fix
for malformed DataTransfer messages.
"""

import asyncio
import websockets
import ssl
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_malformed_datatransfer():
    """Test sending a malformed DataTransfer message"""
    
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
            
            # Send malformed DataTransfer message (like the one causing the error)
            malformed_message = [
                2, "128", "DataTransfer",
                {
                    "vendorId": "Quantex",
                    "messageId": "orderChargingInfo",
                    "data": '{"transactionId":1,"type":"CHARGING","connectorId":0,"soc":0,"chargeTime":300,"chargeEnergy":0,"chargeCost":0,"chargeElecFee":0,"chargeServiceFee":0,"stopReason":"Other","meterValue":12129,"cuspEnergy":0,"cuspElecFee":0,"cuspServiceFee":0,"peakEnergy":0,"peakElecFee":0,"peakServiceFee":0,"flatEnergy":0,"flatElecFee":0,"flatServiceFee":0,"valleyEnergy":0,"valleyElecFee":0,"valleyServiceFee":0,"startTime":"2025-10-12T14:33:16.000Z","stopTime":"2025-10-12T14:38:29.000Z"}'
                }
            ]
            
            print("Sending malformed DataTransfer message...")
            await websocket.send(json.dumps(malformed_message))
            
            # Wait for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"Received response: {response}")
                print("✅ Malformed DataTransfer message handled successfully!")
            except asyncio.TimeoutError:
                print("⚠️ No response received (timeout)")
            
            # Send a proper DataTransfer message for comparison
            proper_message = [
                2, "129", "DataTransfer",
                {
                    "vendorId": "TestVendor",
                    "messageId": "testMessage",
                    "data": "test data"
                }
            ]
            
            print("Sending proper DataTransfer message...")
            await websocket.send(json.dumps(proper_message))
            
            # Wait for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"Received response: {response}")
                print("✅ Proper DataTransfer message handled successfully!")
            except asyncio.TimeoutError:
                print("⚠️ No response received (timeout)")
                
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("Testing malformed DataTransfer message handling...")
    print("Make sure central_system.py is running on localhost:9000")
    asyncio.run(test_malformed_datatransfer())
