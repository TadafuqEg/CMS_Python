# WebSocket Charging Flow Test Guide

## Quick Start

### 1. Generate Token

```bash
node test/generate-token.js
```

Copy the token from the output.

### 2. Run Complete Test

```bash
node test/charging-flow-test.js YOUR_TOKEN CP001
```

This will:
1. Connect to WebSocket gateway
2. Send start_charging command
3. Wait 5 seconds
4. Send stop_charging command
5. Disconnect

## Manual Testing

### Connect to WebSocket

```javascript
const WebSocket = require('ws');
const token = 'YOUR_TOKEN_HERE';
const ws = new WebSocket(`ws://localhost:8080?token=${token}`);
```

### Message Format

All messages follow this format:

```json
{
  "action": "action_name",
  "data": {
    "key": "value"
  }
}
```

## Start Charging

### Message to Send

```json
{
  "action": "start_charging",
  "data": {
    "charger_id": "CP001",
    "connector_id": 1
  }
}
```

### JavaScript Example

```javascript
ws.on('open', () => {
  console.log('Connected!');
  
  // Send start charging command
  ws.send(JSON.stringify({
    action: 'start_charging',
    data: {
      charger_id: 'CP001',
      connector_id: 1
    }
  }));
});
```

### Expected Response

```json
{
  "type": "response",
  "action": "start_charging",
  "data": {
    "success": true,
    "session_id": 123,
    "charger_id": "CP001",
    "message_id": "uuid-here"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

## Stop Charging

### Message to Send

```json
{
  "action": "stop_charging",
  "data": {
    "charger_id": "CP001"
  }
}
```

**Note:** The `charger_id` is optional. If not provided, the system will find the active session for the user.

### JavaScript Example

```javascript
// Stop charging
ws.send(JSON.stringify({
  action: 'stop_charging',
  data: {
    charger_id: 'CP001'  // Optional
  }
}));
```

### Expected Response

```json
{
  "type": "response",
  "action": "stop_charging",
  "data": {
    "success": true,
    "session_id": 123,
    "message_id": "uuid-here",
    "transaction_id": 456
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

## Other Available Actions

### Get Charger Status

```json
{
  "action": "get_charger_status",
  "data": {
    "charger_id": "CP001"
  }
}
```

### Get Active Session

```json
{
  "action": "get_active_session",
  "data": {}
}
```

### List Chargers

```json
{
  "action": "list_chargers",
  "data": {}
}
```

## Complete Test Script

```javascript
const WebSocket = require('ws');

const token = 'YOUR_TOKEN_HERE';
const ws = new WebSocket(`ws://localhost:8080?token=${token}`);

ws.on('open', () => {
  console.log('✅ Connected!');
  
  // Start charging
  console.log('\n📤 Sending start_charging...');
  ws.send(JSON.stringify({
    action: 'start_charging',
    data: {
      charger_id: 'CP001',
      connector_id: 1
    }
  }));
});

ws.on('message', (data) => {
  const message = JSON.parse(data.toString());
  console.log('\n📥 Received:', JSON.stringify(message, null, 2));
  
  if (message.type === 'response' && message.action === 'start_charging') {
    // Wait 5 seconds, then stop
    setTimeout(() => {
      console.log('\n📤 Sending stop_charging...');
      ws.send(JSON.stringify({
        action: 'stop_charging',
        data: {
          charger_id: 'CP001'
        }
      }));
    }, 5000);
  }
  
  if (message.type === 'response' && message.action === 'stop_charging') {
    console.log('\n✅ Test complete!');
    ws.close();
  }
});

ws.on('error', (error) => {
  console.error('❌ Error:', error.message);
});
```

## Using wscat

```bash
# Install wscat
npm install -g wscat

# Connect
wscat -c "ws://localhost:8080?token=YOUR_TOKEN"

# Once connected, send messages:
# Start charging:
{"action":"start_charging","data":{"charger_id":"CP001","connector_id":1}}

# Stop charging:
{"action":"stop_charging","data":{"charger_id":"CP001"}}
```

## Using Browser Console

Open browser console and paste:

```javascript
const token = 'YOUR_TOKEN_HERE';
const ws = new WebSocket(`ws://localhost:8080?token=${token}`);

ws.onopen = () => {
  console.log('Connected!');
  ws.send(JSON.stringify({
    action: 'start_charging',
    data: { charger_id: 'CP001', connector_id: 1 }
  }));
};

ws.onmessage = (e) => {
  console.log('Received:', JSON.parse(e.data));
  
  // After receiving start response, wait and stop
  setTimeout(() => {
    ws.send(JSON.stringify({
      action: 'stop_charging',
      data: { charger_id: 'CP001' }
    }));
  }, 5000);
};
```

## Expected Flow

1. **Connect** → Receive `{"type": "connected", ...}`
2. **Send start_charging** → Receive response with `session_id`
3. **Wait** (optional, for testing)
4. **Send stop_charging** → Receive response with `transaction_id`
5. **Disconnect**

## Error Responses

If something goes wrong, you'll receive:

```json
{
  "type": "error",
  "message": "Error description",
  "timestamp": "2025-01-29T12:00:00Z"
}
```

Or in response:

```json
{
  "type": "response",
  "action": "start_charging",
  "data": {
    "success": false,
    "error": "Error message"
  }
}
```

## Troubleshooting

### Connection Issues

- ✅ Verify token is valid and not expired
- ✅ Check WebSocket URL is correct
- ✅ Ensure gateway is running on port 8080
- ✅ Check firewall settings

### No Response

- ✅ Check Laravel API is accessible
- ✅ Verify Laravel endpoints are working
- ✅ Check Python CMS is running
- ✅ Review gateway logs for errors

### Invalid Action

- ✅ Use exact action names: `start_charging`, `stop_charging`
- ✅ Check data format matches expected structure
- ✅ Verify charger_id exists in system

## Testing Checklist

- [ ] Token generated successfully
- [ ] WebSocket connection established
- [ ] Start charging command sent
- [ ] Start charging response received
- [ ] Session created in database
- [ ] Stop charging command sent
- [ ] Stop charging response received
- [ ] Session updated in database
- [ ] Python CMS received commands
- [ ] Charger received OCPP commands

---

*Last Updated: 2025-01-29*

