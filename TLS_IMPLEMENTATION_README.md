# TLS Implementation with Cipher Suite TLS-ECDHE-RSA-WITH-AES-128-CBC-SHA

This document describes the TLS implementation for the OCPP Central Management System using the specific cipher suite `TLS-ECDHE-RSA-WITH-AES-128-CBC-SHA`.

## Overview

The FastAPI application now supports TLS with a specific cipher suite configuration. The cipher suite `TLS-ECDHE-RSA-WITH-AES-128-CBC-SHA` (OpenSSL notation: `ECDHE-RSA-AES128-SHA`) is used for all HTTPS and WSS connections.

## Implementation Details

### Files Modified

1. **`app/core/config.py`**: 
   - Added `create_ssl_context()` function that creates an SSL context with the specific cipher suite
   - Added `get_ssl_cert_files()` and `get_uvicorn_ssl_kwargs()` helper functions
2. **`app/main.py`**: Updated to use SSL certificates for uvicorn
3. **`app/services/ocpp_handler.py`**: Updated to use the custom SSL context for WebSocket server
4. **`run_fastapi.py`**: Updated startup script to use SSL certificates

### Important Note on Cipher Suite Configuration

**WebSocket Connections (WSS)**: The specific cipher suite `ECDHE-RSA-AES128-SHA` is enforced for all WebSocket connections through the custom SSL context.

**HTTP/HTTPS Connections**: Uvicorn uses the system's default cipher suite selection. The desired cipher suite is typically supported and will be negotiated automatically. To enforce specific cipher suites for HTTP connections, you would need to use a reverse proxy (e.g., nginx) or configure OpenSSL at the system level.

### Cipher Suite Configuration

The implementation uses Python's `ssl` module to configure:
- **Cipher Suite**: `ECDHE-RSA-AES128-SHA` (corresponds to `TLS-ECDHE-RSA-WITH-AES-128-CBC-SHA`)
- **Protocol**: TLS 1.0+ (minimum supported version)
- **Key Exchange**: ECDHE (Elliptic Curve Diffie-Hellman Ephemeral)
- **Authentication**: RSA
- **Encryption**: AES 128-bit in CBC mode
- **MAC**: SHA (Secure Hash Algorithm)

## Setup Instructions

### 1. Generate SSL Certificate

For development and testing, you can generate a self-signed certificate using OpenSSL:

```bash
# Generate a private key
openssl genrsa -out key.pem 2048

# Generate a self-signed certificate (valid for 365 days)
openssl req -new -x509 -key key.pem -out cert.pem -days 365

# Or use the helper script
python generate_ssl_cert.py
```

For production, use a certificate from a trusted Certificate Authority (CA).

### 2. Configure Certificate Paths

Update your `.env` file or environment variables:

```bash
SSL_KEYFILE=key.pem
SSL_CERTFILE=cert.pem
```

Or set them in the `config.py`:

```python
SSL_KEYFILE: str = "key.pem"
SSL_CERTFILE: str = "cert.pem"
```

### 3. Start the Server

Run the FastAPI server with TLS enabled:

```bash
python run_fastapi.py
```

Or run directly:

```bash
python app/main.py
```

### 4. Access the Server

Once the server is running with TLS enabled:

- **HTTPS API**: `https://localhost:8000`
- **WSS OCPP**: `wss://localhost:1025/ocpp/{charger_id}`
- **API Documentation**: `https://localhost:8000/docs`

## Verification

### Test TLS Connection

Use the provided test script to verify the cipher suite:

```bash
python test_tls_cipher.py
```

This will connect to the server and display:
- TLS version
- Cipher suite being used
- Connection status

Example output:
```
============================================================
TLS Cipher Suite Verification Test
============================================================
Testing: localhost:8000

Connecting to localhost:8000...
✓ Connected successfully
✓ TLS Version: TLSv1.2
✓ Cipher Suite: ('ECDHE-RSA-AES128-SHA', 'TLSv1.2', 128)

Cipher Details:
  Name: ECDHE-RSA-AES128-SHA
  Version: TLSv1.2

✓ SUCCESS: Correct cipher suite is being used!
============================================================
Test PASSED
```

### Test with OpenSSL

You can also test with OpenSSL command line:

```bash
openssl s_client -connect localhost:8000 -cipher ECDHE-RSA-AES128-SHA
```

Look for the cipher suite in the output:
```
Cipher    : ECDHE-RSA-AES128-SHA
```

### Test with cURL

Test the HTTPS endpoint:

```bash
curl -k https://localhost:8000
```

The `-k` flag skips certificate verification (use only for testing with self-signed certificates).

## Configuration Options

### Disabling TLS

To run without TLS, either:

1. Set empty certificate paths in configuration:
   ```python
   SSL_KEYFILE: str = ""
   SSL_CERTFILE: str = ""
   ```

2. Don't provide certificate files when starting the server

### Using Different Cipher Suites

To use a different cipher suite, modify the `create_ssl_context()` function in `app/core/config.py`:

```python
# Change this line:
context.set_ciphers('ECDHE-RSA-AES128-SHA')

# To your desired cipher suite, for example:
context.set_ciphers('ECDHE-RSA-AES256-GCM-SHA384')  # TLS 1.2+ only
context.set_ciphers('ECDHE-RSA-AES128-GCM-SHA256')  # TLS 1.2+ only
context.set_ciphers('ECDHE-RSA-AES128-SHA')         # TLS 1.0+ (current)
```

### Cipher Suite Alternatives

If you need different cipher suites, common options include:

- `ECDHE-RSA-AES128-SHA` (current) - TLS 1.0+ compatible
- `ECDHE-RSA-AES256-SHA` - TLS 1.0+ compatible
- `ECDHE-RSA-AES128-GCM-SHA256` - TLS 1.2+ only
- `ECDHE-RSA-AES256-GCM-SHA384` - TLS 1.2+ only
- `ECDHE-RSA-CHACHA20-POLY1305` - TLS 1.2+, modern and fast

## Security Considerations

### Production Deployment

1. **Use a valid certificate** from a trusted CA (Let's Encrypt, commercial CA, etc.)
2. **Configure proper security settings**:
   ```python
   context.minimum_version = ssl.TLSVersion.TLSv1_2  # Use TLS 1.2+ in production
   context.verify_mode = ssl.CERT_REQUIRED  # Verify certificates
   context.check_hostname = True  # Check hostname matches certificate
   ```
3. **Consider enabling TLS 1.2+ only** for better security
4. **Regular certificate renewal** and monitoring

### TLS 1.0/1.1 Deprecation

The current implementation supports TLS 1.0+ for maximum compatibility. For production:

- Consider using TLS 1.2+ only
- Update `minimum_version` to `ssl.TLSVersion.TLSv1_2`
- Use stronger cipher suites like `ECDHE-RSA-AES256-GCM-SHA384`

## Troubleshooting

### Certificate Errors

If you see certificate errors:
- Ensure both `key.pem` and `cert.pem` exist
- Check file permissions (should be readable)
- Verify certificate is not expired
- For testing, use self-signed certificates with `-k` flag

### Cipher Suite Not Supported

If the cipher suite is not available:
- Check OpenSSL version: `openssl version`
- Verify Python SSL support: `python -c "import ssl; print(ssl.OPENSSL_VERSION)"`
- Try an alternative cipher suite

### Connection Refused

If connection fails:
- Verify server is running: `netstat -an | grep 8000`
- Check firewall settings
- Ensure correct port in configuration

## API Endpoints

With TLS enabled, all endpoints are available over HTTPS:

### REST API
- `GET https://localhost:8000/` - Root endpoint
- `GET https://localhost:8000/docs` - API documentation
- `GET https://localhost:8000/api/health` - Health check
- `GET https://localhost:8000/api/chargers` - List chargers
- Various OCPP control endpoints

### WebSocket Endpoints
- `wss://localhost:1025/ocpp/{charger_id}` - Charger OCPP connection
- `wss://localhost:1025/master` - Master monitoring connection
- `wss://localhost:8000/dashboard` - Dashboard connection

## References

- [OpenSSL Cipher Suites](https://www.openssl.org/docs/manmaster/man1/ciphers.html)
- [Python SSL Module](https://docs.python.org/3/library/ssl.html)
- [OCPP 1.6 Specification](https://www.openchargealliance.org/downloads/)
- [TLS Cipher Suite Registry](https://www.iana.org/assignments/tls-parameters/tls-parameters.xhtml)
