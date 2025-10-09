#!/usr/bin/env python3
"""
Test RemoteStartTransaction with proper connection handling
"""

import asyncio
import json
import websockets
import ssl

async def test_remote_start_with_connection():
    """Test RemoteStartTransaction with proper OCPP connection"""
    
    uri = "wss://localhost:9000/CP001"
    
    print(f"🔌 Connecting to {uri}...")
    
    try:
        # Create SSL context that doesn't verify certificates (for testing)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        async with websockets.connect(uri, subprotocols=["ocpp1.6"], ssl=ssl_context) as websocket:
            print("✅ Connected to OCPP server")
            
            # First, send a BootNotification to establish the connection properly
            boot_message = [
                2,  # CALL
                "boot_001",  # Message ID
                "BootNotification",  # Action
                {
                    "chargePointVendor": "Test Vendor",
                    "chargePointModel": "Test Model",
                    "chargePointSerialNumber": "TEST123",
                    "chargeBoxSerialNumber": "BOX123",
                    "firmwareVersion": "1.0.0"
                }
            ]
            
            print(f"📤 Sending BootNotification: {json.dumps(boot_message)}")
            await websocket.send(json.dumps(boot_message))
            
            # Wait for BootNotification response
            boot_response = await websocket.recv()
            print(f"📥 BootNotification Response: {boot_response}")
            
            # Parse BootNotification response
            boot_data = json.loads(boot_response)
            if boot_data[0] == 3:  # CALLRESULT
                print("✅ BootNotification accepted!")
            else:
                print("❌ BootNotification failed!")
                return
            
            # Wait a moment
            await asyncio.sleep(1)
            
            # Now send RemoteStartTransaction command
            remote_start_message = [
                2,  # CALL
                "remote_start_001",  # Message ID
                "RemoteStartTransaction",  # Action
                {
                    "connectorId": 1,
                    "idTag": "RFID123456789"
                }
            ]
            
            print(f"📤 Sending RemoteStartTransaction: {json.dumps(remote_start_message)}")
            await websocket.send(json.dumps(remote_start_message))
            
            # Wait for RemoteStartTransaction response
            response = await websocket.recv()
            print(f"📥 RemoteStartTransaction Response: {response}")
            
            # Parse response
            response_data = json.loads(response)
            if response_data[0] == 3:  # CALLRESULT
                print("✅ RemoteStartTransaction accepted!")
                print(f"Status: {response_data[2]}")
            elif response_data[0] == 4:  # CALLERROR
                print("❌ RemoteStartTransaction failed!")
                print(f"Error Code: {response_data[2]}")
                print(f"Error Description: {response_data[3]}")
                if len(response_data) > 4:
                    print(f"Error Details: {response_data[4]}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

async def main():
    """Main function"""
    print("🔌 OCPP RemoteStartTransaction Test (Fixed)")
    print("=" * 50)
    await test_remote_start_with_connection()

if __name__ == "__main__":
    asyncio.run(main())
