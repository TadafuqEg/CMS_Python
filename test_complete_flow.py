#!/usr/bin/env python3
"""
Test complete RemoteStartTransaction flow
"""

import asyncio
import json
import websockets
import ssl

async def test_complete_flow():
    """Test complete RemoteStartTransaction flow"""
    
    print("🔌 Testing Complete RemoteStartTransaction Flow")
    print("=" * 50)
    
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
        print("\n🚀 Sending RemoteStartTransaction directly to charger...")
        
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
        try:
            response = await asyncio.wait_for(charger_ws.recv(), timeout=5.0)
            print(f"📥 Response: {response}")
            
            # Parse response
            response_data = json.loads(response)
            if response_data[0] == 3:  # CALLRESULT
                print("✅ RemoteStartTransaction accepted!")
                print(f"Status: {response_data[2]}")
            elif response_data[0] == 4:  # CALLERROR
                print("❌ RemoteStartTransaction failed!")
                print(f"Error: {response_data[2]} - {response_data[3]}")
            
        except asyncio.TimeoutError:
            print("⏰ Timeout waiting for response")
        
        # Keep connection alive
        await asyncio.sleep(2)

async def main():
    """Main function"""
    await test_complete_flow()

if __name__ == "__main__":
    asyncio.run(main())
