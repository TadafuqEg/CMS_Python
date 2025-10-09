#!/usr/bin/env python3
"""
Test working RemoteStartTransaction flow
"""

import asyncio
import json
import websockets
import ssl

async def test_working_remote_start():
    """Test working RemoteStartTransaction flow"""
    
    print("🔌 Testing Working RemoteStartTransaction")
    print("=" * 45)
    
    charger_uri = "wss://localhost:9000/CP001"
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    # Connect charger
    async with websockets.connect(charger_uri, subprotocols=["ocpp1.6"], ssl=ssl_context) as charger_ws:
        print("✅ Charger connected to OCPP server")
        
        # Send BootNotification
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
        await charger_ws.send(json.dumps(boot_message))
        
        # Wait for BootNotification response
        boot_response = await charger_ws.recv()
        print(f"📥 BootNotification Response: {boot_response}")
        
        # Parse BootNotification response
        boot_data = json.loads(boot_response)
        if boot_data[0] == 3:  # CALLRESULT
            print("✅ BootNotification accepted!")
        else:
            print("❌ BootNotification failed!")
            return
        
        # Now send RemoteStartTransaction directly to the charger
        print("\n🚀 Sending RemoteStartTransaction to charger...")
        
        remote_start_message = [
            2,  # CALL
            "remote_start_001",  # Message ID
            "RemoteStartTransaction",  # Action
            {
                "connectorId": 1,
                "idTag": "RFID123456789"
            }
        ]
        
        print(f"📤 Sending: {json.dumps(remote_start_message)}")
        await charger_ws.send(json.dumps(remote_start_message))
        
        # Wait for response
        response = await charger_ws.recv()
        print(f"📥 Response: {response}")
        
        # Parse response
        response_data = json.loads(response)
        if response_data[0] == 3:  # CALLRESULT
            print("✅ RemoteStartTransaction accepted!")
            print(f"Status: {response_data[2]}")
        elif response_data[0] == 4:  # CALLERROR
            print("❌ RemoteStartTransaction failed!")
            print(f"Error: {response_data[2]} - {response_data[3]}")
        
        # Keep connection alive
        await asyncio.sleep(2)

async def main():
    """Main function"""
    await test_working_remote_start()

if __name__ == "__main__":
    asyncio.run(main())
