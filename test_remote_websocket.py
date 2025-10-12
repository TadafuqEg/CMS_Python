#!/usr/bin/env python3
"""
Test WebSocket client for sending remote commands
"""

import asyncio
import json
import websockets

async def send_remote_start_command():
    """Send RemoteStartTransaction command via WebSocket"""
    
    # WebSocket URL - adjust as needed
    uri = "ws://localhost:9000/CP001"
    
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri, subprotocols=["ocpp1.6"]) as websocket:
            print("✅ Connected to OCPP server")
            
            # Send RemoteStartTransaction command
            message = [
                2,  # CALL
                "remote_start_001",  # Message ID
                "RemoteStartTransaction",  # Action
                {
                    "connectorId": 1,
                    "idTag": "RFID123456789"
                }
            ]
            
            print(f"Sending: {json.dumps(message)}")
            await websocket.send(json.dumps(message))
            
            # Wait for response
            response = await websocket.recv()
            print(f"Response: {response}")
            
            # Parse response
            response_data = json.loads(response)
            if response_data[0] == 3:  # CALLRESULT
                print("✅ RemoteStartTransaction accepted!")
                print(f"Status: {response_data[2]}")
            elif response_data[0] == 4:  # CALLERROR
                print("❌ RemoteStartTransaction failed!")
                print(f"Error: {response_data[2]} - {response_data[3]}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

async def main():
    """Main function"""
    print("🔌 OCPP RemoteStartTransaction Test")
    print("=" * 40)
    await send_remote_start_command()

if __name__ == "__main__":
    asyncio.run(main())
