# Single Socket Implementation for OCPP Charging Points Data Forwarding

## Overview

This documentation describes how to implement a single WebSocket socket that receives all data from charging points and forwards it to a master socket with proper JSON message structure.

## Architecture

```
Charging Points → Single Socket → Master Socket
     (CP001)         (Port 1025)      (Master Client)
     (CP002)
     (CP003)
```

## OCPP Message Structure

### Base Message Format

All OCPP messages follow this JSON array structure:

```json
[message_type, message_id, action_or_payload, payload_or_error]
```

### Message Types

| Type | Name | Description | Structure |
|------|------|-------------|-----------|
| `2` | CALL | Request from charger to CSMS | `[2, message_id, action, payload]` |
| `3` | CALLRESULT | Response from CSMS to charger | `[3, message_id, payload]` |
| `4` | CALLERROR | Error response from CSMS | `[4, message_id, error_code, error_description, error_details]` |

## Detailed Message Structures

### 1. CALL Messages (Type 2)

**Structure:** `[2, message_id, action, payload]`

#### BootNotification
```json
[
  2,
  "unique-message-id",
  "BootNotification",
  {
    "chargePointVendor": "Vendor Name",
    "chargePointModel": "Model Name",
    "chargePointSerialNumber": "Serial123",
    "chargeBoxSerialNumber": "BoxSerial123",
    "firmwareVersion": "1.0.0",
    "iccid": "ICCID123",
    "imsi": "IMSI123",
    "meterType": "Type A",
    "meterSerialNumber": "Meter123"
  }
]
```

#### StatusNotification
```json
[
  2,
  "unique-message-id",
  "StatusNotification",
  {
    "connectorId": 1,
    "errorCode": "NoError",
    "status": "Available",
    "timestamp": "2025-01-16T10:30:00.000Z",
    "info": "Additional info",
    "vendorId": "Vendor123",
    "vendorErrorCode": "Error123"
  }
]
```

#### StartTransaction
```json
[
  2,
  "unique-message-id",
  "StartTransaction",
  {
    "connectorId": 1,
    "idTag": "RFID123",
    "meterStart": 1000,
    "reservationId": 1,
    "timestamp": "2025-01-16T10:30:00.000Z"
  }
]
```

#### StopTransaction
```json
[
  2,
  "unique-message-id",
  "StopTransaction",
  {
    "transactionId": 12345,
    "timestamp": "2025-01-16T11:30:00.000Z",
    "meterStop": 2000,
    "reason": "Local",
    "idTag": "RFID123",
    "transactionData": [
      {
        "timestamp": "2025-01-16T11:00:00.000Z",
        "sampledValue": [
          {
            "value": "1500",
            "context": "Sample.Periodic",
            "format": "Raw",
            "measurand": "Energy.Active.Import.Register",
            "phase": "L1",
            "location": "Outlet",
            "unit": "Wh"
          }
        ]
      }
    ]
  }
]
```

#### MeterValues
```json
[
  2,
  "unique-message-id",
  "MeterValues",
  {
    "connectorId": 1,
    "transactionId": 12345,
    "meterValue": [
      {
        "timestamp": "2025-01-16T11:00:00.000Z",
        "sampledValue": [
          {
            "value": "1500",
            "context": "Sample.Periodic",
            "format": "Raw",
            "measurand": "Energy.Active.Import.Register",
            "phase": "L1",
            "location": "Outlet",
            "unit": "Wh"
          },
          {
            "value": "230",
            "context": "Sample.Periodic",
            "format": "Raw",
            "measurand": "Voltage",
            "phase": "L1",
            "location": "Outlet",
            "unit": "V"
          }
        ]
      }
    ]
  }
]
```

#### Heartbeat
```json
[
  2,
  "unique-message-id",
  "Heartbeat",
  {}
]
```

### 2. CALLRESULT Messages (Type 3)

**Structure:** `[3, message_id, payload]`

#### BootNotification Response
```json
[
  3,
  "unique-message-id",
  {
    "currentTime": "2025-01-16T10:30:00.000Z",
    "interval": 300,
    "status": "Accepted"
  }
]
```

#### StatusNotification Response
```json
[
  3,
  "unique-message-id",
  {}
]
```

#### StartTransaction Response
```json
[
  3,
  "unique-message-id",
  {
    "transactionId": 12345,
    "idTagInfo": {
      "status": "Accepted",
      "expiryDate": "2025-12-31T23:59:59.000Z",
      "parentIdTag": "Parent123"
    }
  }
]
```

#### StopTransaction Response
```json
[
  3,
  "unique-message-id",
  {
    "idTagInfo": {
      "status": "Accepted",
      "expiryDate": "2025-12-31T23:59:59.000Z",
      "parentIdTag": "Parent123"
    }
  }
]
```

#### MeterValues Response
```json
[
  3,
  "unique-message-id",
  {}
]
```

#### Heartbeat Response
```json
[
  3,
  "unique-message-id",
  {
    "currentTime": "2025-01-16T10:30:00.000Z"
  }
]
```

### 3. CALLERROR Messages (Type 4)

**Structure:** `[4, message_id, error_code, error_description, error_details]`

#### Generic Error
```json
[
  4,
  "unique-message-id",
  "NotImplemented",
  "The requested Action is not known by receiver",
  {}
]
```

#### Property Constraint Violation
```json
[
  4,
  "unique-message-id",
  "PropertyConstraintViolation",
  "A property is not valid",
  {
    "property": "key"
  }
]
```

## Master Socket Message Format

When forwarding messages to the master socket, wrap the original OCPP message with additional metadata:

### Forwarded Message Structure

```json
{
  "message_type": "ocpp_forward",
  "timestamp": "2025-01-16T10:30:00.000Z",
  "charger_id": "CP001",
  "connection_id": "conn-uuid-123",
  "direction": "incoming|outgoing",
  "ocpp_message": [2, "msg-id", "BootNotification", {...}],
  "processing_time_ms": 15.5,
  "source": "ocpp_handler"
}
```

### Example Forwarded Messages

#### Forwarded BootNotification
```json
{
  "message_type": "ocpp_forward",
  "timestamp": "2025-01-16T10:30:00.000Z",
  "charger_id": "CP001",
  "connection_id": "conn-uuid-123",
  "direction": "incoming",
  "ocpp_message": [
    2,
    "boot-msg-123",
    "BootNotification",
    {
      "chargePointVendor": "Vendor Name",
      "chargePointModel": "Model Name",
      "chargePointSerialNumber": "Serial123",
      "firmwareVersion": "1.0.0"
    }
  ],
  "processing_time_ms": 12.3,
  "source": "ocpp_handler"
}
```

#### Forwarded StatusNotification
```json
{
  "message_type": "ocpp_forward",
  "timestamp": "2025-01-16T10:35:00.000Z",
  "charger_id": "CP001",
  "connection_id": "conn-uuid-123",
  "direction": "incoming",
  "ocpp_message": [
    2,
    "status-msg-456",
    "StatusNotification",
    {
      "connectorId": 1,
      "errorCode": "NoError",
      "status": "Available",
      "timestamp": "2025-01-16T10:35:00.000Z"
    }
  ],
  "processing_time_ms": 8.7,
  "source": "ocpp_handler"
}
```

#### Forwarded Response
```json
{
  "message_type": "ocpp_forward",
  "timestamp": "2025-01-16T10:35:05.000Z",
  "charger_id": "CP001",
  "connection_id": "conn-uuid-123",
  "direction": "outgoing",
  "ocpp_message": [
    3,
    "boot-msg-123",
    {
      "currentTime": "2025-01-16T10:35:05.000Z",
      "interval": 300,
      "status": "Accepted"
    }
  ],
  "processing_time_ms": 5.2,
  "source": "ocpp_handler"
}
```

## Implementation Example

### Python WebSocket Server

```python
import asyncio
import json
import websockets
from datetime import datetime
from typing import Dict, Set

class OCPPForwarder:
    def __init__(self):
        self.charger_connections: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.master_connections: Set[websockets.WebSocketServerProtocol] = set()
    
    async def handle_charger_connection(self, websocket, path):
        """Handle individual charger connections"""
        charger_id = path.split('/')[-1]  # Extract charger ID from path
        self.charger_connections[charger_id] = websocket
        
        try:
            async for message in websocket:
                await self.forward_to_masters(charger_id, message, "incoming")
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.charger_connections.pop(charger_id, None)
    
    async def handle_master_connection(self, websocket, path):
        """Handle master socket connections"""
        self.master_connections.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            self.master_connections.discard(websocket)
    
    async def forward_to_masters(self, charger_id: str, message: str, direction: str):
        """Forward message to all master connections"""
        if not self.master_connections:
            return
        
        # Parse original OCPP message
        try:
            ocpp_message = json.loads(message)
        except json.JSONDecodeError:
            return
        
        # Create forwarded message
        forwarded_message = {
            "message_type": "ocpp_forward",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "charger_id": charger_id,
            "connection_id": f"conn-{charger_id}",
            "direction": direction,
            "ocpp_message": ocpp_message,
            "processing_time_ms": 0.0,
            "source": "ocpp_handler"
        }
        
        # Send to all master connections
        disconnected_masters = set()
        for master_ws in self.master_connections:
            try:
                await master_ws.send(json.dumps(forwarded_message))
            except websockets.exceptions.ConnectionClosed:
                disconnected_masters.add(master_ws)
        
        # Clean up disconnected masters
        self.master_connections -= disconnected_masters

# Usage
async def main():
    forwarder = OCPPForwarder()
    
    # Start server for charger connections
    charger_server = await websockets.serve(
        forwarder.handle_charger_connection,
        "0.0.0.0",
        1025,
        subprotocols=["ocpp1.6", "ocpp2.0.1"]
    )
    
    # Start server for master connections
    master_server = await websockets.serve(
        forwarder.handle_master_connection,
        "0.0.0.0",
        1026
    )
    
    print("OCPP Forwarder running on ports 1025 (chargers) and 1026 (masters)")
    await asyncio.gather(charger_server.wait_closed(), master_server.wait_closed())

if __name__ == "__main__":
    asyncio.run(main())
```

## Connection URLs

### Charging Points
```
wss://your-server:1025/ocpp/{charger_id}
```

### Master Socket
```
wss://your-server:1026/master
```

## Error Handling

### Invalid JSON
```json
{
  "message_type": "error",
  "timestamp": "2025-01-16T10:30:00.000Z",
  "charger_id": "CP001",
  "error": "Invalid JSON format",
  "raw_message": "invalid json string"
}
```

### Connection Errors
```json
{
  "message_type": "connection_event",
  "timestamp": "2025-01-16T10:30:00.000Z",
  "charger_id": "CP001",
  "event": "disconnected",
  "reason": "WebSocket connection closed"
}
```

## Best Practices

1. **Message Validation**: Always validate incoming JSON before forwarding
2. **Error Handling**: Wrap all operations in try-catch blocks
3. **Connection Management**: Track active connections and clean up properly
4. **Logging**: Log all forwarded messages for debugging
5. **Performance**: Use async/await for non-blocking operations
6. **Security**: Implement authentication for master socket connections
7. **Monitoring**: Track message counts and processing times

## Testing

### Test Charger Connection
```javascript
const ws = new WebSocket('wss://localhost:1025/ocpp/CP001', ['ocpp1.6']);
ws.onopen = () => {
    // Send BootNotification
    ws.send(JSON.stringify([
        2,
        "test-msg-1",
        "BootNotification",
        {
            "chargePointVendor": "Test Vendor",
            "chargePointModel": "Test Model",
            "chargePointSerialNumber": "TEST123"
        }
    ]));
};
```

### Test Master Connection
```javascript
const masterWs = new WebSocket('wss://localhost:1026/master');
masterWs.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Received forwarded message:', data);
};
```
