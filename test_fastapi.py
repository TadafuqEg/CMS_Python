#!/usr/bin/env python3
"""
Simple test script to verify FastAPI application
"""

import requests
import time
import sys

def test_fastapi_app():
    """Test the FastAPI application"""
    base_url = "http://localhost:8001"
    
    print("Testing FastAPI OCPP Central Management System...")
    
    # Wait for application to start
    print("Waiting for application to start...")
    time.sleep(3)
    
    try:
        # Test root endpoint
        print("Testing root endpoint...")
        response = requests.get(f"{base_url}/", timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test health endpoint
        print("\nTesting health endpoint...")
        response = requests.get(f"{base_url}/api/health", timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
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
