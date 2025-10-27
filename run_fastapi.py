#!/usr/bin/env python3
"""
FastAPI OCPP Central Management System Startup Script
"""

import os
import ssl
import uvicorn
from app.main import app
from app.core.config import settings

# Override ports to avoid conflicts
os.environ["PORT"] = "8001"
os.environ["OCPP_WEBSOCKET_PORT"] = "1025"

# Configure cipher suites globally by monkey-patching SSLContext
# This ensures all SSL contexts use our cipher suite configuration
_original_sslcontext_load_cert_chain = ssl.SSLContext.load_cert_chain

def load_cert_chain_with_ciphers(self, *args, **kwargs):
    """Wrapper for load_cert_chain that also sets cipher suites"""
    result = _original_sslcontext_load_cert_chain(self, *args, **kwargs)
    
    # Configure cipher suites to support TLS-ECDHE-RSA-WITH-AES-128-CBC-SHA
    try:
        self.set_ciphers('ECDHE-RSA-AES128-SHA:ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        self.minimum_version = ssl.TLSVersion.TLSv1_2
    except ssl.SSLError as e:
        print(f"Warning: Could not set cipher suites: {e}")
    
    return result

# Monkey-patch SSLContext to use our custom load_cert_chain
ssl.SSLContext.load_cert_chain = load_cert_chain_with_ciphers

if __name__ == "__main__":
    # Configure cipher suites to support TLS-ECDHE-RSA-WITH-AES-128-CBC-SHA
    ssl_kwargs = {}
    if os.path.exists("cert.pem") and os.path.exists("key.pem"):
        ssl_kwargs = {
            'ssl_keyfile': 'key.pem',
            'ssl_certfile': 'cert.pem'
        }
        print("SSL certificates loaded. Cipher suites configured via monkey-patch.")
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info",
        **ssl_kwargs
    )
