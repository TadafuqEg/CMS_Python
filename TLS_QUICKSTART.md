# TLS Quick Start Guide

## Quick Setup (5 minutes)

### Step 1: Generate SSL Certificate

Run the helper script to generate a self-signed certificate:

```bash
python generate_ssl_cert.py
```

This will create:
- `key.pem` - Private key
- `cert.pem` - SSL certificate

### Step 2: Start the Server

Run the FastAPI server:

```bash
python run_fastapi.py
```

Or:

```bash
python app/main.py
```

The server will start with TLS enabled if certificate files are present.

### Step 3: Test the TLS Connection

Verify that the server is using the correct cipher suite:

```bash
python test_tls_cipher.py
```

Expected output:
```
✓ SUCCESS: Correct cipher suite is being used!
```

## What Was Implemented?

1. **TLS with Specific Cipher Suite**: `TLS-ECDHE-RSA-WITH-AES-128-CBC-SHA`
2. **FastAPI HTTPS Support**: REST API runs over HTTPS
3. **WebSocket WSS Support**: OCPP WebSocket connections run over WSS
4. **Automatic Certificate Loading**: Detects and loads certificates automatically

## Access Points

Once the server is running with TLS:

- **HTTPS**: `https://localhost:8000`
- **API Docs**: `https://localhost:8000/docs`
- **Health Check**: `https://localhost:8000/api/health`
- **OCPP WSS**: `wss://localhost:1025/ocpp/{charger_id}`

## Troubleshooting

### "Certificate files not found" warning

Generate certificates:
```bash
python generate_ssl_cert.py
```

### "Cipher suite not available" error

Your OpenSSL version may not support the cipher suite. Check OpenSSL version:
```bash
openssl version
```

Update OpenSSL if needed:
- Windows: https://slproweb.com/products/Win32OpenSSL.html
- Linux: `sudo apt-get update && sudo apt-get install openssl`
- macOS: `brew upgrade openssl`

### Certificate errors in browser

For self-signed certificates, browsers will show a warning. Click "Advanced" → "Proceed anyway".

### Disable TLS

To run without TLS, set empty certificate paths:
```python
# In .env or config.py
SSL_KEYFILE=""
SSL_CERTFILE=""
```

## Production Deployment

For production:

1. **Use a real certificate** from a trusted CA (Let's Encrypt recommended)
2. **Set minimum TLS version to 1.2** in `app/core/config.py`:
   ```python
   context.minimum_version = ssl.TLSVersion.TLSv1_2
   ```
3. **Enable certificate verification**:
   ```python
   context.check_hostname = True
   context.verify_mode = ssl.CERT_REQUIRED
   ```

## Files Modified

- `app/core/config.py` - Added `create_ssl_context()` function
- `app/main.py` - Updated to use SSL context
- `app/services/ocpp_handler.py` - Updated WebSocket server to use SSL context
- `run_fastapi.py` - Updated to use SSL context

## New Files

- `generate_ssl_cert.py` - Helper script to generate certificates
- `test_tls_cipher.py` - Script to test TLS configuration
- `TLS_IMPLEMENTATION_README.md` - Detailed documentation
- `TLS_QUICKSTART.md` - This file

## Testing Checklist

- [ ] Generate SSL certificates
- [ ] Start server with TLS
- [ ] Verify HTTPS connection works
- [ ] Test cipher suite with test script
- [ ] Test WSS connection for OCPP
- [ ] Review logs for any SSL errors

## Need Help?

See `TLS_IMPLEMENTATION_README.md` for detailed information about:
- Configuration options
- Security considerations
- Cipher suite alternatives
- Advanced troubleshooting
