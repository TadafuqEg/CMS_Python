#!/usr/bin/env python3
"""
Test script to verify charger creation on WebSocket connect and BootNotification data saving
"""

import asyncio
import json
import websockets
import requests
import time
from datetime import datetime

# Test configuration
WEBSOCKET_URL = "ws://localhost:8000"
FASTAPI_URL = "http://localhost:8000"
CHARGER_ID = "TEST_CHARGER_001"

async def test_websocket_connection_and_boot_notification():
    """Test WebSocket connection and BootNotification data saving"""
    
    print("🔌 Testing WebSocket Connection and BootNotification Data Saving")
    print("=" * 60)
    
    # Step 1: Check if charger exists before connection
    print(f"\n1️⃣ Checking charger {CHARGER_ID} before WebSocket connection...")
    try:
        response = requests.get(f"{FASTAPI_URL}/api/chargers/{CHARGER_ID}")
        if response.status_code == 200:
            charger_data = response.json()
            print(f"   ✅ Charger exists: {charger_data['vendor']} {charger_data['model']}")
            print(f"   📊 Status: {charger_data['status']}, Connected: {charger_data['is_connected']}")
        else:
            print(f"   ❌ Charger not found (status: {response.status_code})")
    except Exception as e:
        print(f"   ❌ Error checking charger: {e}")
    
    # Step 2: Connect to WebSocket
    print(f"\n2️⃣ Connecting to WebSocket: {WEBSOCKET_URL}/ocpp/{CHARGER_ID}")
    try:
        async with websockets.connect(f"{WEBSOCKET_URL}/ocpp/{CHARGER_ID}") as websocket:
            print(f"   ✅ WebSocket connected successfully")
            
            # Wait a moment for the connection to be processed
            await asyncio.sleep(1)
            
            # Step 3: Check if charger was created/updated after connection
            print(f"\n3️⃣ Checking charger after WebSocket connection...")
            try:
                response = requests.get(f"{FASTAPI_URL}/api/chargers/{CHARGER_ID}")
                if response.status_code == 200:
                    charger_data = response.json()
                    print(f"   ✅ Charger found: {charger_data['vendor']} {charger_data['model']}")
                    print(f"   📊 Status: {charger_data['status']}, Connected: {charger_data['is_connected']}")
                    print(f"   🔗 Connection Time: {charger_data['connection_time']}")
                    
                    # Check configuration data
                    if charger_data.get('configuration'):
                        config = charger_data['configuration']
                        print(f"   ⚙️  Configuration keys: {list(config.keys())}")
                        if 'remote_address' in config:
                            print(f"   🌐 Remote Address: {config['remote_address']}")
                        if 'subprotocol' in config:
                            print(f"   📡 Subprotocol: {config['subprotocol']}")
                else:
                    print(f"   ❌ Charger not found after connection (status: {response.status_code})")
            except Exception as e:
                print(f"   ❌ Error checking charger after connection: {e}")
            
            # Step 4: Send BootNotification
            print(f"\n4️⃣ Sending BootNotification...")
            boot_notification = [
                2,  # MessageType: CALL
                "unique-message-id-123",  # MessageId
                "BootNotification",  # Action
                {
                    "chargePointVendor": "TestVendor",
                    "chargePointModel": "TestModel-2024",
                    "chargePointSerialNumber": "TEST-SERIAL-001",
                    "firmwareVersion": "1.2.3",
                    "chargeBoxSerialNumber": "BOX-SERIAL-001",
                    "meterSerialNumber": "METER-SERIAL-001",
                    "meterType": "AC_3_PHASE"
                }
            ]
            
            await websocket.send(json.dumps(boot_notification))
            print(f"   ✅ BootNotification sent")
            
            # Wait for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                response_data = json.loads(response)
                print(f"   📨 Response received: {response_data}")
                
                if response_data[0] == 3:  # CALLRESULT
                    boot_response = response_data[2]
                    print(f"   ✅ BootNotification accepted: {boot_response['status']}")
                    print(f"   ⏰ Current Time: {boot_response['currentTime']}")
                    print(f"   🔄 Heartbeat Interval: {boot_response['interval']}")
                else:
                    print(f"   ❌ Unexpected response type: {response_data[0]}")
                    
            except asyncio.TimeoutError:
                print(f"   ⏰ Timeout waiting for BootNotification response")
            except Exception as e:
                print(f"   ❌ Error receiving response: {e}")
            
            # Step 5: Check charger data after BootNotification
            print(f"\n5️⃣ Checking charger data after BootNotification...")
            await asyncio.sleep(1)  # Wait for database update
            
            try:
                response = requests.get(f"{FASTAPI_URL}/api/chargers/{CHARGER_ID}")
                if response.status_code == 200:
                    charger_data = response.json()
                    print(f"   ✅ Charger updated:")
                    print(f"      🏷️  Vendor: {charger_data['vendor']}")
                    print(f"      🏷️  Model: {charger_data['model']}")
                    print(f"      🏷️  Serial: {charger_data['serial_number']}")
                    print(f"      🏷️  Firmware: {charger_data['firmware_version']}")
                    print(f"      📊 Status: {charger_data['status']}")
                    print(f"      🔗 Connected: {charger_data['is_connected']}")
                    
                    # Check BootNotification data in configuration
                    if charger_data.get('configuration'):
                        config = charger_data['configuration']
                        if 'boot_notification_data' in config:
                            print(f"   📋 BootNotification data saved:")
                            boot_data = config['boot_notification_data']
                            for key, value in boot_data.items():
                                print(f"      {key}: {value}")
                        
                        if 'charge_box_serial_number' in config:
                            print(f"   📦 Charge Box Serial: {config['charge_box_serial_number']}")
                        if 'meter_serial_number' in config:
                            print(f"   📊 Meter Serial: {config['meter_serial_number']}")
                        if 'meter_type' in config:
                            print(f"   📊 Meter Type: {config['meter_type']}")
                else:
                    print(f"   ❌ Charger not found after BootNotification (status: {response.status_code})")
            except Exception as e:
                print(f"   ❌ Error checking charger after BootNotification: {e}")
            
            # Step 6: Send Heartbeat
            print(f"\n6️⃣ Sending Heartbeat...")
            heartbeat = [
                2,  # MessageType: CALL
                "heartbeat-message-id-456",  # MessageId
                "Heartbeat",  # Action
                {}
            ]
            
            await websocket.send(json.dumps(heartbeat))
            print(f"   ✅ Heartbeat sent")
            
            # Wait for heartbeat response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                response_data = json.loads(response)
                print(f"   📨 Heartbeat response: {response_data}")
                
                if response_data[0] == 3:  # CALLRESULT
                    heartbeat_response = response_data[2]
                    print(f"   ✅ Heartbeat received: {heartbeat_response['currentTime']}")
                else:
                    print(f"   ❌ Unexpected heartbeat response: {response_data[0]}")
                    
            except asyncio.TimeoutError:
                print(f"   ⏰ Timeout waiting for Heartbeat response")
            except Exception as e:
                print(f"   ❌ Error receiving heartbeat response: {e}")
            
            # Step 7: Final charger check
            print(f"\n7️⃣ Final charger status check...")
            try:
                response = requests.get(f"{FASTAPI_URL}/api/chargers/{CHARGER_ID}")
                if response.status_code == 200:
                    charger_data = response.json()
                    print(f"   ✅ Final charger status:")
                    print(f"      📊 Status: {charger_data['status']}")
                    print(f"      🔗 Connected: {charger_data['is_connected']}")
                    print(f"      💓 Last Heartbeat: {charger_data['last_heartbeat']}")
                    print(f"      🔗 Connection Time: {charger_data['connection_time']}")
                else:
                    print(f"   ❌ Final charger check failed (status: {response.status_code})")
            except Exception as e:
                print(f"   ❌ Error in final charger check: {e}")
            
            print(f"\n✅ WebSocket connection test completed")
            
    except Exception as e:
        print(f"   ❌ WebSocket connection failed: {e}")

def test_connection_events():
    """Test connection events logging"""
    print(f"\n📊 Testing Connection Events Logging")
    print("=" * 40)
    
    try:
        # Get connection events for the test charger
        response = requests.get(f"{FASTAPI_URL}/api/connection-events/{CHARGER_ID}")
        if response.status_code == 200:
            events = response.json()
            print(f"   ✅ Found {len(events)} connection events for {CHARGER_ID}")
            
            for event in events[-3:]:  # Show last 3 events
                print(f"      📅 {event['timestamp']}: {event['event_type']}")
                if event.get('remote_address'):
                    print(f"         🌐 Remote: {event['remote_address']}")
                if event.get('reason'):
                    print(f"         📝 Reason: {event['reason']}")
                if event.get('session_duration'):
                    print(f"         ⏱️  Duration: {event['session_duration']}s")
        else:
            print(f"   ❌ No connection events found (status: {response.status_code})")
    except Exception as e:
        print(f"   ❌ Error checking connection events: {e}")

async def main():
    """Main test function"""
    print("🚀 Starting Charger WebSocket Data Test")
    print("=" * 50)
    
    # Test WebSocket connection and BootNotification
    await test_websocket_connection_and_boot_notification()
    
    # Test connection events
    test_connection_events()
    
    print(f"\n🎉 Test completed!")
    print(f"   📝 Check the database for charger {CHARGER_ID}")
    print(f"   🔍 Verify BootNotification data is saved in configuration")
    print(f"   📊 Check connection events are logged")

if __name__ == "__main__":
    asyncio.run(main())
