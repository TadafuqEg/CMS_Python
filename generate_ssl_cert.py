#!/usr/bin/env python3
"""
Generate SSL certificate and private key for TLS testing
Creates a self-signed certificate for development use
"""

import os
import subprocess
import sys

def generate_certificate():
    """
    Generate a self-signed SSL certificate and private key
    """
    print("=" * 60)
    print("SSL Certificate Generator")
    print("=" * 60)
    print()
    
    # Check if openssl is available
    try:
        result = subprocess.run(['openssl', 'version'], 
                              capture_output=True, text=True, check=True)
        print(f"✓ OpenSSL found: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ Error: OpenSSL is not installed or not in PATH")
        print("  Please install OpenSSL to generate certificates")
        print("  Windows: Download from https://slproweb.com/products/Win32OpenSSL.html")
        print("  Linux: sudo apt-get install openssl")
        print("  macOS: brew install openssl")
        sys.exit(1)
    
    print()
    
    # Check if certificate files already exist
    keyfile = "key.pem"
    certfile = "cert.pem"
    
    if os.path.exists(keyfile) and os.path.exists(certfile):
        response = input(f"Certificate files already exist. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Certificate generation cancelled.")
            sys.exit(0)
        print()
    
    print("Generating private key (2048-bit RSA)...")
    try:
        # Generate private key
        subprocess.run([
            'openssl', 'genrsa', '-out', keyfile, '2048'
        ], check=True, capture_output=True)
        print(f"✓ Private key created: {keyfile}")
    except subprocess.CalledProcessError as e:
        print(f"✗ Error generating private key: {e}")
        sys.exit(1)
    
    print()
    print("Generating self-signed certificate...")
    print("(You will be prompted for certificate details)")
    print()
    
    try:
        # Generate self-signed certificate
        # Using default values that work well for localhost
        env = os.environ.copy()
        
        # Try to generate with default values using -subj flag
        subprocess.run([
            'openssl', 'req', '-new', '-x509',
            '-key', keyfile,
            '-out', certfile,
            '-days', '365',
            '-subj', '/C=US/ST=State/L=City/O=Organization/CN=localhost'
        ], check=True, capture_output=True, env=env)
        print(f"✓ Certificate created: {certfile}")
    except subprocess.CalledProcessError as e:
        print(f"✗ Error generating certificate: {e}")
        print("  Try running manually: openssl req -new -x509 -key key.pem -out cert.pem -days 365")
        sys.exit(1)
    
    print()
    print("=" * 60)
    print("Certificate Generation Complete!")
    print("=" * 60)
    print()
    print(f"Private Key: {keyfile}")
    print(f"Certificate: {certfile}")
    print()
    print("Certificate Details:")
    print("-" * 60)
    
    # Display certificate details
    try:
        result = subprocess.run([
            'openssl', 'x509', '-in', certfile, '-noout', '-text'
        ], capture_output=True, text=True, check=True)
        
        # Extract useful information
        for line in result.stdout.split('\n'):
            if any(x in line for x in ['Subject:', 'Issuer:', 'Not Before', 'Not After', 'Validity']):
                print(line.strip())
    except:
        pass
    
    print()
    print("Next Steps:")
    print("1. Update your .env file or config with:")
    print(f'   SSL_KEYFILE="{keyfile}"')
    print(f'   SSL_CERTFILE="{certfile}"')
    print()
    print("2. Start the server:")
    print("   python run_fastapi.py")
    print()
    print("3. Test the TLS connection:")
    print("   python test_tls_cipher.py")
    print()
    print("⚠️  IMPORTANT: This is a self-signed certificate for testing only.")
    print("   For production, use certificates from a trusted Certificate Authority.")
    print()

if __name__ == "__main__":
    try:
        generate_certificate()
    except KeyboardInterrupt:
        print("\n\nCertificate generation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        sys.exit(1)
