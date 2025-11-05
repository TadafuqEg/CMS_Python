# WebSocket Communication Protocol Documentation

## Overview

This document describes the complete communication protocol between:
1. **Mobile App ↔ Node.js WebSocket Gateway** (WebSocket protocol)
2. **Node.js Gateway ↔ Laravel Backend** (HTTP REST API)
3. **Laravel Backend → Node.js Gateway → Mobile App** (Redis Pub/Sub)

---

## Table of Contents

1. [Mobile App → Node.js Gateway (WebSocket)](#1-mobile-app--nodejs-gateway-websocket)
2. [Node.js Gateway → Laravel Backend (HTTP)](#2-nodejs-gateway--laravel-backend-http)
3. [Laravel Backend → Node.js Gateway (Redis Pub/Sub)](#3-laravel-backend--nodejs-gateway-redis-pubsub)
4. [Node.js Gateway → Mobile App (WebSocket)](#4-nodejs-gateway--mobile-app-websocket)
5. [Complete Flow Examples](#5-complete-flow-examples)

---

## 1. Mobile App → Node.js Gateway (WebSocket)

### Connection

**WebSocket URL:**
```
ws://your-domain.com:8080?token=YOUR_JWT_TOKEN
```

or

```
wss://your-domain.com:8080?token=YOUR_JWT_TOKEN
```

**Token:** JWT token obtained from Laravel backend after authentication

### Message Format

All messages from mobile app to Node.js gateway must be valid JSON:

```json
{
  "action": "action_name",
  "data": {
    // Action-specific data
  }
}
```

### Supported Actions

#### 1.1 Start Charging

**Request:**
```json
{
  "action": "start_charging",
  "data": {
    "charger_id": "CP001",
    "connector_id": 1
  }
}
```

**Fields:**
- `charger_id` (string, required): Charger identifier
- `connector_id` (integer, optional): Connector ID (default: 1)

#### 1.2 Stop Charging

**Request:**
```json
{
  "action": "stop_charging",
  "data": {
    "charger_id": "CP001"
  }
}
```

**Fields:**
- `charger_id` (string, optional): Charger identifier. If not provided, stops the user's active session

#### 1.3 Get Charger Status

**Request:**
```json
{
  "action": "get_charger_status",
  "data": {
    "charger_id": "CP001"
  }
}
```

**Fields:**
- `charger_id` (string, required): Charger identifier

#### 1.4 Get Active Session

**Request:**
```json
{
  "action": "get_active_session",
  "data": {}
}
```

**Fields:**
- No additional data required

#### 1.5 List Chargers

**Request:**
```json
{
  "action": "list_chargers",
  "data": {}
}
```

**Fields:**
- No additional data required

---

## 2. Node.js Gateway → Laravel Backend (HTTP)

### Endpoint

**URL:** `POST /api/websocket/message`

**Headers:**
```
Authorization: Bearer {JWT_TOKEN}
Content-Type: application/json
```

### Request Format

```json
{
  "action": "action_name",
  "data": {
    // Action-specific data
  },
  "userId": 123
}
```

**Fields:**
- `action` (string, required): Action name (same as WebSocket action)
- `data` (object, required): Action-specific data
- `userId` (integer, required): User ID extracted from JWT token

### Response Format

```json
{
  "success": true,
  "data": {
    // Response data
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Error message",
  "message": "Detailed error description"
}
```

### Example Requests

#### 2.1 Start Charging Request

**HTTP Request:**
```http
POST /api/websocket/message HTTP/1.1
Host: laravel-backend.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json

{
  "action": "start_charging",
  "data": {
    "charger_id": "CP001",
    "connector_id": 1
  },
  "userId": 123
}
```

**HTTP Response:**
```json
{
  "success": true,
  "data": {
    "session_id": 456,
    "transaction_id": 789,
    "charger_id": "CP001",
    "connector_id": 1,
    "status": "initiated",
    "message": "Charging session started"
  }
}
```

#### 2.2 Stop Charging Request

**HTTP Request:**
```http
POST /api/websocket/message HTTP/1.1
Host: laravel-backend.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json

{
  "action": "stop_charging",
  "data": {
    "charger_id": "CP001"
  },
  "userId": 123
}
```

**HTTP Response:**
```json
{
  "success": true,
  "data": {
    "session_id": 456,
    "transaction_id": 789,
    "status": "stopped",
    "energy_delivered": 15.5,
    "duration": 3600,
    "message": "Charging session stopped"
  }
}
```

---

## 3. Laravel Backend → Node.js Gateway (Redis Pub/Sub)

### Overview

Laravel backend publishes real-time notifications to Redis channels. Node.js gateway subscribes to these channels and forwards messages to connected mobile clients.

### Redis Channels

#### 3.1 User Notifications Channel

**Channel Pattern:** `user:{userId}:notifications`

**Purpose:** General notifications for a user

**Message Format:**
```json
{
  "type": "notification",
  "title": "Notification Title",
  "message": "Notification message",
  "data": {
    // Additional data
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

**Example:**
```json
{
  "type": "notification",
  "title": "Charging Started",
  "message": "Your charging session has started",
  "data": {
    "session_id": 456,
    "charger_id": "CP001"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

#### 3.2 Session Updates Channel

**Channel Pattern:** `user:{userId}:session_updates`

**Purpose:** Real-time updates about charging sessions

**Message Format:**
```json
{
  "type": "session_update",
  "session_id": 456,
  "transaction_id": 789,
  "event": "session_event_name",
  "data": {
    // Session-specific data
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

**Session Events:**
- `session_started`: Charging session started
- `session_stopped`: Charging session stopped
- `meter_value`: Energy meter reading update
- `session_error`: Error occurred during session
- `session_completed`: Session completed successfully

**Example: Session Started**
```json
{
  "type": "session_update",
  "session_id": 456,
  "transaction_id": 789,
  "event": "session_started",
  "data": {
    "charger_id": "CP001",
    "connector_id": 1,
    "id_tag": "RFID123",
    "meter_start": 1000,
    "start_time": "2025-01-29T12:00:00Z"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

**Example: Meter Value Update**
```json
{
  "type": "session_update",
  "session_id": 456,
  "transaction_id": 789,
  "event": "meter_value",
  "data": {
    "charger_id": "CP001",
    "connector_id": 1,
    "energy_delivered": 5.5,
    "power": 7.2,
    "voltage": 230,
    "current": 31.3,
    "meter_value": 5500,
    "timestamp": "2025-01-29T12:05:00Z"
  },
  "timestamp": "2025-01-29T12:05:00Z"
}
```

**Example: Session Stopped**
```json
{
  "type": "session_update",
  "session_id": 456,
  "transaction_id": 789,
  "event": "session_stopped",
  "data": {
    "charger_id": "CP001",
    "connector_id": 1,
    "meter_stop": 15500,
    "energy_delivered": 14.5,
    "duration": 3600,
    "stop_time": "2025-01-29T13:00:00Z",
    "stop_reason": "RemoteStop"
  },
  "timestamp": "2025-01-29T13:00:00Z"
}
```

#### 3.3 Charger Updates Channel

**Channel Pattern:** `user:{userId}:charger_updates`

**Purpose:** Real-time updates about charger status

**Message Format:**
```json
{
  "type": "charger_update",
  "charger_id": "CP001",
  "event": "charger_event_name",
  "data": {
    // Charger-specific data
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

**Charger Events:**
- `status_changed`: Charger status changed
- `connector_status_changed`: Connector status changed
- `error`: Charger error occurred
- `configuration_changed`: Charger configuration changed

**Example: Status Changed**
```json
{
  "type": "charger_update",
  "charger_id": "CP001",
  "event": "status_changed",
  "data": {
    "status": "Charging",
    "previous_status": "Available",
    "connector_id": 1,
    "timestamp": "2025-01-29T12:00:00Z"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

**Example: Connector Status Changed**
```json
{
  "type": "charger_update",
  "charger_id": "CP001",
  "event": "connector_status_changed",
  "data": {
    "connector_id": 1,
    "status": "Occupied",
    "previous_status": "Available",
    "error_code": null,
    "timestamp": "2025-01-29T12:00:00Z"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

### Laravel Publishing Example

**PHP Code:**
```php
use Illuminate\Support\Facades\Redis;

// Publish to user notifications channel
Redis::publish("user:{$userId}:notifications", json_encode([
    'type' => 'notification',
    'title' => 'Charging Started',
    'message' => 'Your charging session has started',
    'data' => [
        'session_id' => 456,
        'charger_id' => 'CP001'
    ],
    'timestamp' => now()->toIso8601String()
]));

// Publish to session updates channel
Redis::publish("user:{$userId}:session_updates", json_encode([
    'type' => 'session_update',
    'session_id' => 456,
    'transaction_id' => 789,
    'event' => 'meter_value',
    'data' => [
        'charger_id' => 'CP001',
        'connector_id' => 1,
        'energy_delivered' => 5.5,
        'power' => 7.2,
        'meter_value' => 5500,
        'timestamp' => now()->toIso8601String()
    ],
    'timestamp' => now()->toIso8601String()
]));
```

---

## 4. Node.js Gateway → Mobile App (WebSocket)

### Message Types

#### 4.1 Connection Confirmation

**Type:** `connected`

**Message:**
```json
{
  "type": "connected",
  "timestamp": "2025-01-29T12:00:00Z",
  "userId": 123
}
```

#### 4.2 Action Response

**Type:** `response`

**Message:**
```json
{
  "type": "response",
  "action": "start_charging",
  "data": {
    "success": true,
    "session_id": 456,
    "transaction_id": 789,
    "charger_id": "CP001",
    "message": "Charging session started"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

**Error Response:**
```json
{
  "type": "response",
  "action": "start_charging",
  "data": {
    "success": false,
    "error": "Charger not available",
    "message": "The requested charger is currently unavailable"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

#### 4.3 Real-time Notification (from Redis)

**Type:** `notification`

**Message:**
```json
{
  "type": "notification",
  "title": "Charging Started",
  "message": "Your charging session has started",
  "data": {
    "session_id": 456,
    "charger_id": "CP001"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

#### 4.4 Session Update (from Redis)

**Type:** `session_update`

**Message:**
```json
{
  "type": "session_update",
  "session_id": 456,
  "transaction_id": 789,
  "event": "meter_value",
  "data": {
    "charger_id": "CP001",
    "connector_id": 1,
    "energy_delivered": 5.5,
    "power": 7.2,
    "meter_value": 5500,
    "timestamp": "2025-01-29T12:05:00Z"
  },
  "timestamp": "2025-01-29T12:05:00Z"
}
```

#### 4.5 Charger Update (from Redis)

**Type:** `charger_update`

**Message:**
```json
{
  "type": "charger_update",
  "charger_id": "CP001",
  "event": "status_changed",
  "data": {
    "status": "Charging",
    "previous_status": "Available",
    "connector_id": 1,
    "timestamp": "2025-01-29T12:00:00Z"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

#### 4.6 Error Message

**Type:** `error`

**Message:**
```json
{
  "type": "error",
  "message": "Invalid message format",
  "timestamp": "2025-01-29T12:00:00Z"
}
```

---

## 5. Complete Flow Examples

### Example 1: Start Charging Flow

**1. Mobile App → Node.js Gateway:**
```json
{
  "action": "start_charging",
  "data": {
    "charger_id": "CP001",
    "connector_id": 1
  }
}
```

**2. Node.js Gateway → Laravel Backend (HTTP):**
```http
POST /api/websocket/message HTTP/1.1
Authorization: Bearer {token}
Content-Type: application/json

{
  "action": "start_charging",
  "data": {
    "charger_id": "CP001",
    "connector_id": 1
  },
  "userId": 123
}
```

**3. Laravel Backend → Node.js Gateway → Mobile App (Redis Pub/Sub):**
```json
// Published to: user:123:session_updates
{
  "type": "session_update",
  "session_id": 456,
  "transaction_id": 789,
  "event": "session_started",
  "data": {
    "charger_id": "CP001",
    "connector_id": 1,
    "id_tag": "RFID123",
    "meter_start": 1000,
    "start_time": "2025-01-29T12:00:00Z"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

**4. Node.js Gateway → Mobile App (WebSocket Response):**
```json
{
  "type": "response",
  "action": "start_charging",
  "data": {
    "success": true,
    "session_id": 456,
    "transaction_id": 789,
    "charger_id": "CP001",
    "message": "Charging session started"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

### Example 2: Real-time Meter Value Updates

**1. Python CMS → Laravel Backend (via internal event):**
```json
{
  "event": "meter_value",
  "charger_id": "CP001",
  "transaction_id": 789,
  "data": {
    "energy_delivered": 5.5,
    "power": 7.2,
    "meter_value": 5500
  }
}
```

**2. Laravel Backend → Redis (Publish):**
```php
// Published to: user:123:session_updates
Redis::publish("user:123:session_updates", json_encode([
    'type' => 'session_update',
    'session_id' => 456,
    'transaction_id' => 789,
    'event' => 'meter_value',
    'data' => [
        'charger_id' => 'CP001',
        'connector_id' => 1,
        'energy_delivered' => 5.5,
        'power' => 7.2,
        'meter_value' => 5500,
        'timestamp' => now()->toIso8601String()
    ],
    'timestamp' => now()->toIso8601String()
]));
```

**3. Node.js Gateway → Mobile App (WebSocket):**
```json
{
  "type": "session_update",
  "session_id": 456,
  "transaction_id": 789,
  "event": "meter_value",
  "data": {
    "charger_id": "CP001",
    "connector_id": 1,
    "energy_delivered": 5.5,
    "power": 7.2,
    "meter_value": 5500,
    "timestamp": "2025-01-29T12:05:00Z"
  },
  "timestamp": "2025-01-29T12:05:00Z"
}
```

### Example 3: Stop Charging Flow

**1. Mobile App → Node.js Gateway:**
```json
{
  "action": "stop_charging",
  "data": {
    "charger_id": "CP001"
  }
}
```

**2. Node.js Gateway → Laravel Backend (HTTP):**
```http
POST /api/websocket/message HTTP/1.1
Authorization: Bearer {token}
Content-Type: application/json

{
  "action": "stop_charging",
  "data": {
    "charger_id": "CP001"
  },
  "userId": 123
}
```

**3. Laravel Backend → Redis (Publish):**
```php
// Published to: user:123:session_updates
Redis::publish("user:123:session_updates", json_encode([
    'type' => 'session_update',
    'session_id' => 456,
    'transaction_id' => 789,
    'event' => 'session_stopped',
    'data' => [
        'charger_id' => 'CP001',
        'connector_id' => 1,
        'meter_stop' => 15500,
        'energy_delivered' => 14.5,
        'duration' => 3600,
        'stop_time' => now()->toIso8601String(),
        'stop_reason' => 'RemoteStop'
    ],
    'timestamp' => now()->toIso8601String()
]));
```

**4. Node.js Gateway → Mobile App (WebSocket Response):**
```json
{
  "type": "response",
  "action": "stop_charging",
  "data": {
    "success": true,
    "session_id": 456,
    "transaction_id": 789,
    "status": "stopped",
    "energy_delivered": 14.5,
    "duration": 3600,
    "message": "Charging session stopped"
  },
  "timestamp": "2025-01-29T13:00:00Z"
}
```

---

## Redis Channel Summary

| Channel Pattern | Purpose | Message Type |
|----------------|---------|--------------|
| `user:{userId}:notifications` | General notifications | `notification` |
| `user:{userId}:session_updates` | Charging session updates | `session_update` |
| `user:{userId}:charger_updates` | Charger status updates | `charger_update` |

---

## Error Handling

### Connection Errors

**Connection Rejected:**
```
WebSocket Close Code: 1008
Reason: "Authentication required" or "Invalid authentication token"
```

**Server at Capacity:**
```
WebSocket Close Code: 1008
Reason: "Server at capacity"
```

### Message Errors

**Invalid Message Format:**
```json
{
  "type": "error",
  "message": "Invalid message format",
  "timestamp": "2025-01-29T12:00:00Z"
}
```

**Action Error:**
```json
{
  "type": "response",
  "action": "start_charging",
  "data": {
    "success": false,
    "error": "Charger not available",
    "message": "The requested charger is currently unavailable"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

---

## Heartbeat

The WebSocket connection uses ping/pong for heartbeat:
- **Ping Interval:** 30 seconds (configurable)
- **Timeout:** Connection closed if no pong received

---

## Best Practices

1. **Always handle connection errors** - Implement reconnection logic
2. **Validate message format** - Check for required fields before sending
3. **Handle all message types** - Listen for responses, notifications, and errors
4. **Use proper error handling** - Display user-friendly error messages
5. **Implement reconnection** - Handle network interruptions gracefully
6. **Rate limiting** - Don't send messages too frequently
7. **Message queuing** - Queue messages when disconnected

---

## Testing

### Using wscat

```bash
wscat -c "ws://localhost:8080?token=YOUR_TOKEN"
```

### Using JavaScript

```javascript
const ws = new WebSocket('ws://localhost:8080?token=YOUR_TOKEN');

ws.onopen = () => {
  console.log('Connected');
  
  ws.send(JSON.stringify({
    action: 'start_charging',
    data: { charger_id: 'CP001', connector_id: 1 }
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Received:', message);
};
```

---

*Last Updated: 2025-01-29*

