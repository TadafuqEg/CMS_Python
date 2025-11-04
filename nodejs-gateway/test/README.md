# Test Tools

## Generate Test Token

### Method 1: Using config (recommended)

This uses the JWT configuration from your `.env` file:

```bash
node test/generate-token.js
```

With custom user ID:
```bash
node test/generate-token.js 456 test@example.com
```

### Method 2: Simple generator

This doesn't require config file:

```bash
node test/generate-token-simple.js YOUR_SECRET_KEY
```

With user ID and email:
```bash
node test/generate-token-simple.js YOUR_SECRET_KEY 123 user@example.com
```

## WebSocket Test Client

Open `websocket-client.html` in your browser:

1. Open the file in a web browser
2. Enter WebSocket URL: `ws://localhost:8080`
3. Paste your JWT token
4. Click "Connect"
5. Send test messages

## Test Connection with wscat

```bash
# Install wscat globally
npm install -g wscat

# Connect with token
wscat -c "ws://localhost:8080?token=YOUR_TOKEN_HERE"

# Once connected, send message:
{"action": "start_charging", "data": {"charger_id": "CP001"}}
```

## Verify Token

You can decode the token to see its contents at: https://jwt.io

Paste your token there to see the payload.

## Example Test Flow

1. Generate token:
   ```bash
   node test/generate-token.js
   ```

2. Copy the token

3. Open `test/websocket-client.html` in browser

4. Paste token and connect

5. Send test message:
   ```json
   {
     "action": "start_charging",
     "data": {
       "charger_id": "CP001"
     }
   }
   ```

