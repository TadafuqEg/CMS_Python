# Universal WebSocket Server

This project includes a universal WebSocket server that runs on port 9001 and broadcasts messages to clients connected to port 9000.

## Architecture

```
Universal Client (9001) → Universal Server (9001) → Broadcast to Target Clients (9000)
```

## Files

- `universal_websocket.py` - The universal WebSocket server
- `test_universal_websocket.py` - Test clients to demonstrate functionality
- `central_system.py` - OCPP server running on port 9000
- `interceptor.py` - Interceptor running on port 9100

## How to Use

### 1. Start the Central System (Port 9000)
```bash
python central_system.py
```

### 2. Start the Universal WebSocket Server (Port 9001)
```bash
python universal_websocket.py
```

### 3. Test the System
```bash
python test_universal_websocket.py
```

## How It Works

1. **Universal Server (Port 9001)**: Accepts secure WSS connections from any client
2. **Message Broadcasting**: When a message is received on port 9001, it's broadcasted to all clients connected to port 9000
3. **Bidirectional Communication**: Messages from port 9000 clients are also forwarded back to universal clients

## Features

- **SSL/TLS Support**: Both servers use secure WebSocket connections (WSS)
- **Multiple Client Support**: Can handle multiple clients connected to both ports
- **Automatic Cleanup**: Disconnected clients are automatically removed
- **Error Handling**: Robust error handling for connection issues
- **Logging**: Comprehensive logging for debugging

## Example Usage

### Sending a Message via Universal WebSocket
```python
import asyncio
import ssl
import websockets
import json

async def send_message():
    # SSL context for secure connection
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    async with websockets.connect("wss://localhost:9001", ssl=ssl_context) as ws:
        message = {
            "action": "test",
            "data": "Hello World"
        }
        await ws.send(json.dumps(message))
        print("Message sent!")

asyncio.run(send_message())
```

### Receiving Messages on Target Port
```python
import asyncio
import ssl
import websockets

async def receive_messages():
    # SSL context for secure connection
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    async with websockets.connect("wss://localhost:9000/test_cp", ssl=ssl_context) as ws:
        async for message in ws:
            print(f"Received: {message}")

asyncio.run(receive_messages())
```

## Configuration

You can modify the following constants in `universal_websocket.py`:
- `UNIVERSAL_PORT = 9001` - Port for the universal server
- `TARGET_PORT = 9000` - Port to broadcast to
- `TARGET_HOST = "localhost"` - Host to broadcast to
