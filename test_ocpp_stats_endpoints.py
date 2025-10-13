#!/usr/bin/env python3
"""
Test script to demonstrate the new OCPP stats endpoints
"""

import requests
import json
from datetime import datetime

# Base URL for the FastAPI server
BASE_URL = "http://localhost:8000/api"

def test_stats_endpoints():
    """Test all the new stats endpoints"""
    
    print("🔍 Testing OCPP Stats Endpoints")
    print("=" * 50)
    
    # Test 1: Get comprehensive stats
    print("\n1. 📊 Testing /stats endpoint (comprehensive stats)")
    try:
        response = requests.get(f"{BASE_URL}/stats")
        if response.status_code == 200:
            stats = response.json()
            print("✅ Stats endpoint working")
            print(f"   - Active connections: {stats.get('active_connections', 0)}")
            print(f"   - Messages sent: {stats.get('messages_sent', 0)}")
            print(f"   - Messages received: {stats.get('messages_received', 0)}")
            print(f"   - Active chargers: {len(stats.get('active_chargers', []))}")
        else:
            print(f"❌ Stats endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Stats endpoint error: {e}")
    
    # Test 2: Get active connections
    print("\n2. 🔌 Testing /connections endpoint (active connections)")
    try:
        response = requests.get(f"{BASE_URL}/connections")
        if response.status_code == 200:
            connections = response.json()
            print("✅ Connections endpoint working")
            print(f"   - Found {len(connections)} active connections")
            for conn in connections:
                print(f"   - {conn['charger_id']}: {conn['status']}")
        else:
            print(f"❌ Connections endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Connections endpoint error: {e}")
    
    # Test 3: Get stats summary
    print("\n3. 📈 Testing /stats/summary endpoint (quick summary)")
    try:
        response = requests.get(f"{BASE_URL}/stats/summary")
        if response.status_code == 200:
            summary = response.json()
            print("✅ Stats summary endpoint working")
            print(f"   - Total connections: {summary.get('total_connections', 0)}")
            print(f"   - Active connections: {summary.get('active_connections', 0)}")
            print(f"   - Connected charger IDs: {summary.get('connected_charger_ids', [])}")
        else:
            print(f"❌ Stats summary endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Stats summary endpoint error: {e}")
    
    # Test 4: Get specific charger connection (if any chargers are connected)
    print("\n4. 🎯 Testing /connections/{charger_id} endpoint")
    try:
        # First get the list of connected chargers
        response = requests.get(f"{BASE_URL}/stats/summary")
        if response.status_code == 200:
            summary = response.json()
            charger_ids = summary.get('connected_charger_ids', [])
            
            if charger_ids:
                charger_id = charger_ids[0]  # Test with first connected charger
                response = requests.get(f"{BASE_URL}/connections/{charger_id}")
                if response.status_code == 200:
                    charger_info = response.json()
                    print(f"✅ Specific charger endpoint working for {charger_id}")
                    print(f"   - Status: {charger_info.get('status', 'Unknown')}")
                    print(f"   - Connected: {charger_info.get('is_connected', False)}")
                    print(f"   - Vendor: {charger_info.get('vendor', 'Unknown')}")
                    print(f"   - Model: {charger_info.get('model', 'Unknown')}")
                else:
                    print(f"❌ Specific charger endpoint failed: {response.status_code}")
            else:
                print("ℹ️  No chargers connected to test specific charger endpoint")
        else:
            print("❌ Could not get charger list for testing")
    except Exception as e:
        print(f"❌ Specific charger endpoint error: {e}")
    
    print("\n" + "=" * 50)
    print("🏁 Testing completed!")

if __name__ == "__main__":
    test_stats_endpoints()
