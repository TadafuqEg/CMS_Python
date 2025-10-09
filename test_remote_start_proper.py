#!/usr/bin/env python3
"""
Proper test for RemoteStartTransaction - using the central system's method
"""

import asyncio
import json
import websockets
import ssl
from central_system import client_manager

async def establish_connection():
    """Establish a proper OCPP connection first"""
    uri = "wss://localhost:9000/CP001"
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    async with websockets.connect(uri, subprotocols=["ocpp1.6"], ssl=ssl_context) as websocket:
        print("✅ Connected to OCPP server")
        
        # Send BootNotification to establish connection
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
        
        print(f"📤 Sending BootNotification...")
        await websocket.send(json.dumps(boot_message))
        
        # Wait for BootNotification response
        boot_response = await websocket.recv()
        print(f"📥 BootNotification Response: {boot_response}")
        
        # Parse BootNotification response
        boot_data = json.loads(boot_response)
        if boot_data[0] == 3:  # CALLRESULT
            print("✅ BootNotification accepted!")
            return True
        else:
            print("❌ BootNotification failed!")
            return False

async def test_remote_start_proper():
    """Test RemoteStartTransaction using the proper method"""
    
    print("🔌 Testing RemoteStartTransaction (Proper Method)")
    print("=" * 50)
    
    # First establish connection
    if not await establish_connection():
        return
    
    # Wait a moment for the connection to be registered
    await asyncio.sleep(2)
    
    # Now use the central system's method to send RemoteStartTransaction
    print("\n🚀 Sending RemoteStartTransaction using central system method...")
    
    try:
        result = await client_manager.send_remote_start_to_charger(
            charger_id="CP001",
            id_tag="RFID123456789",
            connector_id=1
        )
        print(f"✅ RemoteStartTransaction sent successfully!")
        print(f"Response: {result}")
        
    except Exception as e:
        print(f"❌ Error sending RemoteStartTransaction: {e}")
        print("Available chargers:", list(client_manager.clients.keys()))

async def main():
    """Main function"""
    await test_remote_start_proper()

if __name__ == "__main__":
    asyncio.run(main())
