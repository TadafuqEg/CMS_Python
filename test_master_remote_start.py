#!/usr/bin/env python3
"""
Test sending RemoteStartTransaction from master socket
"""

import asyncio
import json
import websockets
import ssl

async def test_master_remote_start():
    """Test sending RemoteStartTransaction from master socket"""
    
    print("🔌 Testing RemoteStartTransaction from Master Socket")
    print("=" * 55)
    
    # First, establish a charger connection
    charger_uri = "wss://localhost:9000/CP001"
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    # Connect charger first
    async with websockets.connect(charger_uri, subprotocols=["ocpp1.6"], ssl=ssl_context) as charger_ws:
        print("✅ Charger connected to OCPP server")
        
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
        
        # Now connect to master socket
        master_uri = "wss://localhost:9000/master"
        
        async with websockets.connect(master_uri, ssl=ssl_context) as master_ws:
            print("✅ Master socket connected")
            
            # Send RemoteStartTransaction command via master socket
            remote_start_message = [
                2,  # CALL
                "remote_start_001",  # Message ID
                "RemoteStartTransaction",  # Action
                {
                    "connectorId": 1,
                    "idTag": "RFID123456789"
                }
            ]
            
            print(f"📤 Sending RemoteStartTransaction from master socket...")
            print(f"Message: {json.dumps(remote_start_message)}")
            
            # Send the command via master socket
            await master_ws.send(json.dumps(remote_start_message))
            
            # Wait for response from charger
            print("⏳ Waiting for response from charger...")
            
            try:
                # Wait for response from charger connection
                response = await asyncio.wait_for(charger_ws.recv(), timeout=10.0)
                print(f"📥 Response from charger: {response}")
                
                # Parse response
                response_data = json.loads(response)
                if response_data[0] == 3:  # CALLRESULT
                    print("✅ RemoteStartTransaction accepted by charger!")
                    print(f"Status: {response_data[2]}")
                elif response_data[0] == 4:  # CALLERROR
                    print("❌ RemoteStartTransaction failed!")
                    print(f"Error Code: {response_data[2]}")
                    print(f"Error Description: {response_data[3]}")
                
            except asyncio.TimeoutError:
                print("⏰ Timeout waiting for response from charger")
            
            # Keep connections alive for a bit
            await asyncio.sleep(2)

async def main():
    """Main function"""
    await test_master_remote_start()

if __name__ == "__main__":
    asyncio.run(main())
