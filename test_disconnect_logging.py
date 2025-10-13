#!/usr/bin/env python3
"""
Test script to verify disconnect event logging
"""

import requests
import json
import time

def test_disconnect_logging():
    """Test disconnect event logging"""
    
    print("🔍 Testing Disconnect Event Logging")
    print("=" * 50)
    
    # Get current events
    print("\n1. 📊 Current connection events:")
    try:
        response = requests.get("http://localhost:8000/api/connection-events")
        if response.status_code == 200:
            events = response.json()
            print(f"   Total events: {len(events)}")
            
            # Show recent events
            for event in events[:5]:  # Show last 5 events
                print(f"   - {event['event_type']} for {event['charger_id']} at {event['timestamp']}")
                if event['event_type'] == 'DISCONNECT':
                    print(f"     Reason: {event.get('reason', 'N/A')}")
                    print(f"     Session Duration: {event.get('session_duration', 'N/A')} seconds")
        else:
            print(f"   Error: {response.status_code}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Get current stats
    print("\n2. 📈 Current OCPP stats:")
    try:
        response = requests.get("http://localhost:8000/api/stats")
        if response.status_code == 200:
            stats = response.json()
            print(f"   Active connections: {stats.get('active_connections', 0)}")
            print(f"   Total connections: {stats.get('connections_total', 0)}")
            print(f"   Connected charger IDs: {[charger['charger_id'] for charger in stats.get('active_chargers', [])]}")
        else:
            print(f"   Error: {response.status_code}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Instructions for testing disconnect
    print("\n3. 🧪 To test disconnect event logging:")
    print("   - Connect an OCPP client to wss://localhost:9000/CP_TEST")
    print("   - Wait for CONNECT event to appear")
    print("   - Disconnect the client")
    print("   - Check for DISCONNECT event with session duration")
    
    print("\n4. 🔄 Monitoring for new events:")
    print("   Run this script again after disconnecting a client to see DISCONNECT events")
    
    print("\n" + "=" * 50)
    print("🏁 Testing completed!")

if __name__ == "__main__":
    test_disconnect_logging()
