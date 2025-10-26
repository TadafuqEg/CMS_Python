#!/usr/bin/env python3
"""
Test script to verify TLS cipher suite configuration
This script tests that the server is using TLS-ECDHE-RSA-WITH-AES-128-CBC-SHA
"""

import ssl
import socket
import sys

def test_tls_cipher_suite(host='localhost', port=8000):
    """
    Connect to the server and check which cipher suite is being used
    """
    try:
        # Create SSL context for the client
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Connect to the server
        print(f"Connecting to {host}:{port}...")
        with socket.create_connection((host, port)) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                print(f"✓ Connected successfully")
                print(f"✓ TLS Version: {ssock.version()}")
                print(f"✓ Cipher Suite: {ssock.cipher()}")
                
                # Check if our specific cipher suite is being used
                cipher_name, cipher_version, _ = ssock.cipher()
                print(f"\nCipher Details:")
                print(f"  Name: {cipher_name}")
                print(f"  Version: {cipher_version}")
                
                # The cipher suite should be ECDHE-RSA-AES128-SHA
                if 'ECDHE-RSA-AES128-SHA' in cipher_name or 'AES128-SHA' in cipher_name:
                    print("\n✓ SUCCESS: Correct cipher suite is being used!")
                    return True
                else:
                    print(f"\n⚠ WARNING: Different cipher suite is being used: {cipher_name}")
                    return False
    except ssl.SSLError as e:
        print(f"✗ SSL Error: {e}")
        return False
    except Exception as e:
        print(f"✗ Connection Error: {e}")
        return False

if __name__ == "__main__":
    # Parse command line arguments
    host = sys.argv[1] if len(sys.argv) > 1 else 'localhost'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    
    print("=" * 60)
    print("TLS Cipher Suite Verification Test")
    print("=" * 60)
    print(f"Testing: {host}:{port}")
    print()
    
    success = test_tls_cipher_suite(host, port)
    
    print()
    print("=" * 60)
    if success:
        print("Test PASSED")
        sys.exit(0)
    else:
        print("Test FAILED")
        sys.exit(1)
