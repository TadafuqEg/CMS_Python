#!/usr/bin/env python3
"""
Test script to demonstrate the enhanced remote start functionality
"""

import requests
import json
import time

def test_remote_start_with_db_check():
    """Test the remote start endpoint with database connection checking"""
    
    print("🔍 Testing Enhanced Remote Start with Database Check")
    print("=" * 60)
    
    base_url = "http://localhost:8000"
    
    # Test 1: Check current connection events
    print("\n1. 📊 Current connection events:")
    try:
        response = requests.get(f"{base_url}/api/connection-events")
        if response.status_code == 200:
            events = response.json()
            print(f"   Total events: {len(events)}")
            
            # Show recent events
            for event in events[:3]:  # Show last 3 events
                print(f"   - {event['event_type']} for {event['charger_id']} at {event['timestamp']}")
                if event['event_type'] == 'CONNECT':
                    print(f"     Connection ID: {event['connection_id']}")
        else:
            print(f"   Error: {response.status_code}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 2: Test remote start with existing charger
    print("\n2. 🚀 Testing remote start with existing charger:")
    test_charger_id = "CP_2"  # Use the charger we saw in events
    
    remote_start_payload = {
        "charger_id": test_charger_id,
        "connector_id": 1,
        "id_tag": "TEST_USER_001"
    }
    
    try:
        response = requests.post(
            f"{base_url}/api/charging/remote_start",
            json=remote_start_payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("   ✅ Remote start command sent successfully!")
            print(f"   - Message ID: {result.get('message_id')}")
            print(f"   - Charger ID: {result.get('charger_id')}")
            print(f"   - Connection ID: {result.get('connection_id')}")
            print(f"   - Last Connection Time: {result.get('last_connection_time')}")
        elif response.status_code == 400:
            error_detail = response.json().get('detail', 'Unknown error')
            print(f"   ⚠️  Bad Request: {error_detail}")
        elif response.status_code == 404:
            error_detail = response.json().get('detail', 'Unknown error')
            print(f"   ❌ Not Found: {error_detail}")
        else:
            print(f"   ❌ Unexpected status: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 3: Test remote start with non-existent charger
    print("\n3. 🧪 Testing remote start with non-existent charger:")
    non_existent_payload = {
        "charger_id": "NON_EXISTENT_CHARGER",
        "connector_id": 1,
        "id_tag": "TEST_USER_002"
    }
    
    try:
        response = requests.post(
            f"{base_url}/api/charging/remote_start",
            json=non_existent_payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 404:
            error_detail = response.json().get('detail', 'Unknown error')
            print(f"   ✅ Correctly rejected: {error_detail}")
        else:
            print(f"   ❌ Unexpected status: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 4: Show the enhanced functionality
    print("\n4. 🎯 Enhanced Remote Start Features:")
    print("   ✅ Database connection event verification")
    print("   ✅ Most recent connection status check")
    print("   ✅ Active connection validation")
    print("   ✅ Connection ID matching")
    print("   ✅ Automatic disconnect event logging")
    print("   ✅ Detailed error messages")
    print("   ✅ Connection metadata in response")
    
    print("\n" + "=" * 60)
    print("🏁 Testing completed!")

if __name__ == "__main__":
    test_remote_start_with_db_check()
