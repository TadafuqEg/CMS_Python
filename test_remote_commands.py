#!/usr/bin/env python3
"""
Test script for sending remote commands to OCPP chargers
"""

import asyncio
import json
import websockets
from central_system import client_manager

async def test_remote_start_transaction():
    """Test sending RemoteStartTransaction command"""
    charger_id = "CP001"
    id_tag = "RFID123456789"
    connector_id = 1
    
    print(f"Testing RemoteStartTransaction to {charger_id}...")
    
    try:
        # Check if charger is connected
        if charger_id not in client_manager.clients:
            print(f"❌ Charger {charger_id} is not connected")
            print("Available chargers:", list(client_manager.clients.keys()))
            return
        
        # Send remote start command
        result = await client_manager.send_remote_start_to_charger(
            charger_id=charger_id,
            id_tag=id_tag,
            connector_id=connector_id
        )
        
        print(f"✅ RemoteStartTransaction sent successfully!")
        print(f"Response: {result}")
        
    except Exception as e:
        print(f"❌ Error sending RemoteStartTransaction: {e}")

async def test_remote_stop_transaction():
    """Test sending RemoteStopTransaction command"""
    charger_id = "CP001"
    transaction_id = 1
    
    print(f"Testing RemoteStopTransaction to {charger_id}...")
    
    try:
        # Check if charger is connected
        if charger_id not in client_manager.clients:
            print(f"❌ Charger {charger_id} is not connected")
            return
        
        # Send remote stop command
        result = await client_manager.send_remote_stop_to_charger(
            charger_id=charger_id,
            transaction_id=transaction_id
        )
        
        print(f"✅ RemoteStopTransaction sent successfully!")
        print(f"Response: {result}")
        
    except Exception as e:
        print(f"❌ Error sending RemoteStopTransaction: {e}")

async def list_connected_chargers():
    """List all connected chargers"""
    print("Connected chargers:")
    if client_manager.clients:
        for charger_id in client_manager.clients.keys():
            print(f"  - {charger_id}")
    else:
        print("  No chargers connected")

async def main():
    """Main test function"""
    print("🔌 OCPP Remote Commands Test")
    print("=" * 40)
    
    # List connected chargers
    await list_connected_chargers()
    print()
    
    # Test remote start
    await test_remote_start_transaction()
    print()
    
    # Wait a bit
    await asyncio.sleep(2)
    
    # Test remote stop
    await test_remote_stop_transaction()

if __name__ == "__main__":
    asyncio.run(main())
