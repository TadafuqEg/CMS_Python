#!/usr/bin/env python3
"""
Simple OCPP test to isolate the issue
"""

import asyncio
import json
import websockets
import ssl

async def test_simple_ocpp():
    """Test simple OCPP communication"""
    
    uri = "wss://localhost:9000/CP001"
    
    print(f"🔌 Connecting to {uri}...")
    
    try:
        # Create SSL context that doesn't verify certificates (for testing)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        async with websockets.connect(uri, subprotocols=["ocpp1.6"], ssl=ssl_context) as websocket:
            print("✅ Connected to OCPP server")
            
            # Send a simple Heartbeat message
            heartbeat_message = [
                2,  # CALL
                "heartbeat_001",  # Message ID
                "Heartbeat",  # Action
                {}
            ]
            
            print(f"📤 Sending Heartbeat: {json.dumps(heartbeat_message)}")
            await websocket.send(json.dumps(heartbeat_message))
            
            # Wait for response
            response = await websocket.recv()
            print(f"📥 Heartbeat Response: {response}")
            
            # Parse response
            response_data = json.loads(response)
            if response_data[0] == 3:  # CALLRESULT
                print("✅ Heartbeat successful!")
                print(f"Current time: {response_data[2]}")
            elif response_data[0] == 4:  # CALLERROR
                print("❌ Heartbeat failed!")
                print(f"Error Code: {response_data[2]}")
                print(f"Error Description: {response_data[3]}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

async def main():
    """Main function"""
    print("🔌 Simple OCPP Test")
    print("=" * 30)
    await test_simple_ocpp()

if __name__ == "__main__":
    asyncio.run(main())
