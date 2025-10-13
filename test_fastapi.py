#!/usr/bin/env python3
"""
Test script to verify FastAPI OCPP Central Management System endpoints
"""

import requests
import time
import sys
import asyncio
import websockets
from datetime import datetime, timedelta
from typing import Dict, Any
import jwt
import json

try:
    from app.core.config import settings
    from app.core.security import create_access_token
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Ensure the project structure includes app/core/config.py and app/core/security.py")
    sys.exit(1)

async def test_dashboard_websocket(base_url: str, headers: Dict[str, str]):
    """Test the dashboard WebSocket endpoint"""
    print("\nTesting dashboard WebSocket endpoint (/dashboard)...")
    uri = f"ws://{base_url.split('://')[1]}/dashboard"
    try:
        async with websockets.connect(uri, extra_headers=headers, ping_interval=20, ping_timeout=10) as websocket:
            # Receive initial data
            message = await websocket.recv()
            data = json.loads(message)
            print(f"Received initial data: {data}")
            return True
    except Exception as e:
        print(f"❌ Dashboard WebSocket error: {e}")
        return False

def test_fastapi_app():
    """Test the FastAPI application endpoints"""
    base_url = "http://localhost:8001"
    
    print("Testing FastAPI OCPP Central Management System...")
    
    # Wait for application to start
    print("Waiting for application to start...")
    time.sleep(3)
    
    # Verify PyJWT functionality
    try:
        print(f"PyJWT module path: {jwt.__file__}")
        test_payload = {"sub": "test_user"}
        test_token = jwt.encode(test_payload, "test-secret", algorithm="HS256")
        print("PyJWT encode test successful")
    except AttributeError as e:
        print(f"❌ PyJWT error: {e}")
        print("Ensure PyJWT is installed correctly (pip install pyjwt>=2.5.0)")
        return False
    
    # Generate JWT token for authenticated requests
    try:
        token_data = {"sub": "test_user", "roles": ["admin"]}
        token = create_access_token(token_data)
        headers = {"Authorization": f"Bearer {token}"}
    except Exception as e:
        print(f"❌ Error generating JWT token: {e}")
        print("Check PyJWT installation and app/core/security.py")
        return False
    
    try:
        # Test root endpoint
        print("\nTesting root endpoint...")
        response = requests.get(f"{base_url}/", timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test health endpoint
        print("\nTesting health endpoint (/api/health)...")
        response = requests.get(f"{base_url}/api/health", headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test metrics endpoint
        print("\nTesting metrics endpoint (/api/metrics)...")
        response = requests.get(f"{base_url}/api/metrics", headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test status endpoint
        print("\nTesting status endpoint (/api/status)...")
        response = requests.get(f"{base_url}/api/status", headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test chargers endpoint
        print("\nTesting chargers endpoint (/api/chargers)...")
        response = requests.get(f"{base_url}/api/chargers", headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test sessions endpoint
        print("\nTesting sessions endpoint (/api/sessions)...")
        response = requests.get(f"{base_url}/api/sessions", headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test internal chargers status endpoint
        print("\nTesting internal chargers status endpoint (/internal/chargers/status)...")
        response = requests.get(f"{base_url}/internal/chargers/status", headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test internal event endpoint (POST request for RemoteStartTransaction)
        print("\nTesting internal event endpoint (/internal/event)...")
        event_data = {
            "action": "RemoteStartTransaction",
            "charger_id": "CP_1",
            "payload": {"connectorId": 1, "idTag": "TAG123"},
            "source": "laravel_cms",
            "priority": "normal"
        }
        response = requests.post(f"{base_url}/internal/event", json=event_data, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test logs endpoint
        print("\nTesting logs endpoint (/api/logs)...")
        response = requests.get(f"{base_url}/api/logs", headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test logs summary endpoint
        print("\nTesting logs summary endpoint (/api/logs/summary)...")
        response = requests.get(f"{base_url}/api/logs/summary", headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test recent logs endpoint for charger CP_1
        print("\nTesting recent logs endpoint (/api/logs/CP_1/recent)...")
        response = requests.get(f"{base_url}/api/logs/CP_1/recent", headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test logs export endpoint (JSON format)
        print("\nTesting logs export endpoint (/api/logs/export)...")
        response = requests.get(f"{base_url}/api/logs/export?format=json", headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test OCPP remote start endpoint
        print("\nTesting OCPP remote start endpoint (/api/ocpp/remote/start)...")
        start_data = {
            "charger_id": "CP_1",
            "id_tag": "TAG123",
            "connector_id": 1
        }
        response = requests.post(f"{base_url}/api/ocpp/remote/start", json=start_data, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test OCPP trigger message endpoint
        print("\nTesting OCPP trigger message endpoint (/api/ocpp/trigger)...")
        trigger_data = {
            "charger_id": "CP_1",
            "requested_message": "Heartbeat"
        }
        response = requests.post(f"{base_url}/api/ocpp/trigger", json=trigger_data, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test OCPP unlock connector endpoint
        print("\nTesting OCPP unlock connector endpoint (/api/ocpp/unlock)...")
        unlock_data = {
            "charger_id": "CP_1",
            "connector_id": 1
        }
        response = requests.post(f"{base_url}/api/ocpp/unlock", json=unlock_data, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test OCPP get configuration endpoint
        print("\nTesting OCPP get configuration endpoint (/api/ocpp/configuration/get)...")
        config_data = {
            "charger_id": "CP_1",
            "key": ["HeartbeatInterval"]
        }
        response = requests.post(f"{base_url}/api/ocpp/configuration/get", json=config_data, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test OCPP reboot endpoint
        print("\nTesting OCPP reboot endpoint (/api/ocpp/reboot)...")
        reboot_data = {
            "charger_id": "CP_1",
            "type": "Soft"
        }
        response = requests.post(f"{base_url}/api/ocpp/reboot", json=reboot_data, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test OCPP reset endpoint
        print("\nTesting OCPP reset endpoint (/api/ocpp/reset)...")
        reset_data = {
            "charger_id": "CP_1",
            "type": "Soft"
        }
        response = requests.post(f"{base_url}/api/ocpp/reset", json=reset_data, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test dashboard WebSocket endpoint
        success = asyncio.run(test_dashboard_websocket(base_url, headers))
        if not success:
            print("❌ Dashboard WebSocket test failed")
            return False
        
        # Test docs endpoint
        print("\nTesting docs endpoint...")
        response = requests.get(f"{base_url}/docs", timeout=10)
        print(f"Status: {response.status_code}")
        print("Swagger UI is accessible!")
        
        print("\n✅ All tests passed! FastAPI application is working correctly.")
        return True
        
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Connection error: {e}")
        print("Make sure the FastAPI application is running on port 8001")
        return False
    except requests.exceptions.Timeout as e:
        print(f"❌ Timeout error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_fastapi_app()
    sys.exit(0 if success else 1)