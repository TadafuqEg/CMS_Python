# WebSocket Communication Protocol Documentation

## Overview

This document describes the complete communication protocol between:
1. **Mobile App → Laravel Backend** (REST API for start/stop charging)
2. **Laravel Backend → Python CMS** (REST API)
3. **Mobile App → Node.js WebSocket Gateway** (WebSocket connection - receive-only)
4. **Laravel Backend → Node.js Gateway → Mobile App** (Redis Pub/Sub for real-time updates)

---

## Table of Contents

1. [Mobile App → Laravel Backend (REST API for Start/Stop)](#1-mobile-app--laravel-backend-rest-api)
2. [Mobile App → Node.js Gateway (WebSocket Connection)](#2-mobile-app--nodejs-gateway-websocket)
3. [Laravel Backend → Node.js Gateway (Redis Pub/Sub)](#3-laravel-backend--nodejs-gateway-redis-pubsub)
4. [Node.js Gateway → Mobile App (WebSocket)](#4-nodejs-gateway--mobile-app-websocket)
5. [Complete Flow Examples](#5-complete-flow-examples)

---

## 1. Mobile App → Laravel Backend (REST API for Start/Stop)

### Overview

**Important:** Mobile apps use REST API endpoints directly to Laravel backend for start/stop charging operations. WebSocket is **NOT** used for sending commands - it is **receive-only** for real-time updates.

### Start Charging

**Endpoint:** `POST /api/charging/start`

**Headers:**
```
Authorization: Bearer {JWT_TOKEN}
Content-Type: application/json
```

**Request:**
```json
{
  "charger_id": "CP001",
  "connector_id": 1
}
```

**Fields:**
- `charger_id` (string, required): Charger/Charging Point identifier
- `connector_id` (integer, optional): Connector ID (default: 1)

**Response:**
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

**Error Response:**
```json
{
  "success": false,
  "error": "Charger not available",
  "message": "The requested charger is currently unavailable"
}
```

### Stop Charging

**Endpoint:** `POST /api/charging/stop`

**Headers:**
```
Authorization: Bearer {JWT_TOKEN}
Content-Type: application/json
```

**Request:**
```json
{
  "charger_id": "CP001"
}
```

**Fields:**
- `charger_id` (string, optional): Charger identifier. If not provided, stops the user's active session

**Response:**
```json
{
  "success": true,
  "data": {
    "session_id": 456,
    "transaction_id": 789,
    "status": "stopped",
    "energy_delivered": 14.5,
    "duration": 3600,
    "message": "Charging session stopped"
  }
}
```

**Flow:**
1. Mobile app calls Laravel REST API (`POST /api/charging/start` or `/api/charging/stop`)
2. Laravel backend calls Python CMS REST API (`POST /api/charging/remote_start` or `/api/charging/stop`)
3. Laravel backend returns response to mobile app
4. Laravel backend publishes updates to Redis for real-time notifications
5. Node.js gateway receives Redis messages and forwards to mobile app via WebSocket

---

## 2. Mobile App → Node.js Gateway (WebSocket Connection)

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

### Important Notes

**WebSocket is RECEIVE-ONLY** - Mobile apps should NOT send any messages via WebSocket. The WebSocket connection is used exclusively for receiving real-time updates from the server.

**What you receive via WebSocket:**
- Charger status updates (for map display)
- Session updates (meter values, session events)
- Active session updates
- Charger list updates
- General notifications

**What you send via REST API:**
- Start charging (`POST /api/charging/start`)
- Stop charging (`POST /api/charging/stop`)

### Charging Station Status Model

Charging stations are displayed on the mobile app map with color-coded icons:

**Station Status Colors:**

1. **Green (Available):** 
   - Station has available connectors
   - Icon displays availability as fraction: `X/Y`
   - `Y` = Total number of connectors at the station
   - `X` = Number of available connectors
   - Example: `3/4` means 3 out of 4 connectors are available

2. **Blue (In Use):**
   - All connectors at the station are currently in use
   - No availability number is displayed
   - Icon shows only the blue lightning bolt

3. **Red (Unavailable):**
   - Station is under maintenance OR all connectors are unavailable
   - No availability number is displayed
   - Icon shows only the red lightning bolt

**Station Structure:**
- **Station:** Physical location (e.g., a parking lot, shopping mall)
- **Charging Point:** Individual charging unit within a station (identified by `charger_id`)
- **Connector:** Individual charging gun/outlet on a charging point (identified by `connector_id`)

**Example:**
- Station "Station A" has:
  - Charging Point "CP001" with 2 connectors (connector_id: 1, 2)
  - Charging Point "CP002" with 2 connectors (connector_id: 1, 2)
  - Total: 4 connectors
  - If 3 are available → Green icon with "3/4"
  - If all 4 are in use → Blue icon (no number)
  - If station is under maintenance → Red icon (no number)

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
    "station_id": "STATION001",
    "station_name": "Cillout Mansoura",
    "station_address": "15 Tahrir Street, Downtown, Cairo",
    "charge_percentage": 50,
    "time_remaining": 1200,
    "time_remaining_display": "20 min",
    "energy_consumed": 42.5,
    "energy_consumed_unit": "kWh",
    "cost": 315,
    "cost_currency": "EGP",
    "charging_duration": 8100,
    "charging_duration_display": "2hr 15min",
    "output_power": 22.0,
    "output_power_unit": "kW",
    "energy_delivered": 42.5,
    "power": 22.0,
    "voltage": 230,
    "current": 95.7,
    "meter_value": 42500,
    "timestamp": "2025-01-29T12:05:00Z"
  },
  "timestamp": "2025-01-29T12:05:00Z"
}
```

**Field Descriptions:**
- `station_name` (string): Name of the charging station
- `station_address` (string): Full address of the charging station
- `charge_percentage` (integer): Current battery charge level (0-100)
- `time_remaining` (integer): Estimated time remaining in seconds
- `time_remaining_display` (string): Human-readable time remaining (e.g., "20 min", "2hr 15min")
- `energy_consumed` (float): Total energy consumed in kWh
- `energy_consumed_unit` (string): Unit for energy consumed (typically "kWh")
- `cost` (float): Total cost of the charging session
- `cost_currency` (string): Currency code (e.g., "EGP", "USD", "EUR")
- `charging_duration` (integer): Total charging duration in seconds
- `charging_duration_display` (string): Human-readable charging duration (e.g., "2hr 15min")
- `output_power` (float): Current output power from the charging gun in kW
- `output_power_unit` (string): Unit for output power (typically "kW")
- `energy_delivered` (float): Total energy delivered (same as energy_consumed, kept for backward compatibility)
- `power` (float): Current power consumption (same as output_power, kept for backward compatibility)
- `voltage` (float): Current voltage in volts
- `current` (float): Current amperage in amps
- `meter_value` (integer): Raw meter reading value (in Wh)

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

**Purpose:** Real-time updates about charger status. These messages are automatically pushed to all connected mobile clients to update the map display.

**Message Format:**
```json
{
  "type": "charger_status_update",
  "station_id": "STATION001",
  "charger_id": "CP001",
  "status": "available",
  "data": {
    "total_connectors": 4,
    "available_connectors": 3,
    "connectors_in_use": 1,
    "connectors_unavailable": 0,
    "display": "3/4",
    "connector_status": [
      {
        "connector_id": 1,
        "status": "Available"
      },
      {
        "connector_id": 2,
        "status": "Available"
      },
      {
        "connector_id": 3,
        "status": "Available"
      },
      {
        "connector_id": 4,
        "status": "Charging"
      }
    ],
    "station_status": "Available",
    "is_under_maintenance": false,
    "timestamp": "2025-01-29T12:00:00Z"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

**Charger Status Values:**
- `available`: Station has available connectors (green icon, shows X/Y fraction)
- `in_use`: All connectors are in use (blue icon, no number)
- `unavailable`: Station under maintenance or all connectors unavailable (red icon, no number)

**Charger Events:**
- `status_changed`: Charger status changed
- `connector_status_changed`: Connector status changed
- `error`: Charger error occurred
- `configuration_changed`: Charger configuration changed
- `maintenance_mode`: Station entered/exited maintenance mode

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
    "station_id": "STATION001",
    "station_name": "Cillout Mansoura",
    "station_address": "15 Tahrir Street, Downtown, Cairo",
    "charge_percentage": 50,
    "time_remaining": 1200,
    "time_remaining_display": "20 min",
    "energy_consumed": 42.5,
    "energy_consumed_unit": "kWh",
    "cost": 315,
    "cost_currency": "EGP",
    "charging_duration": 8100,
    "charging_duration_display": "2hr 15min",
    "output_power": 22.0,
    "output_power_unit": "kW",
    "energy_delivered": 42.5,
    "power": 22.0,
    "voltage": 230,
    "current": 95.7,
    "meter_value": 42500,
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

#### 4.6 Charger Status Update (Pushed from Gateway)

**Type:** `charger_status_update`

**Purpose:** Automatically pushed to mobile clients when charger status changes. Used to update the map display with real-time availability information.

**Message:**
```json
{
  "type": "charger_status_update",
  "station_id": "STATION001",
  "charger_id": "CP001",
  "status": "available",
  "data": {
    "total_connectors": 4,
    "available_connectors": 3,
    "connectors_in_use": 1,
    "connectors_unavailable": 0,
    "display": "3/4",
    "connector_status": [
      {
        "connector_id": 1,
        "status": "Available"
      },
      {
        "connector_id": 2,
        "status": "Available"
      },
      {
        "connector_id": 3,
        "status": "Available"
      },
      {
        "connector_id": 4,
        "status": "Charging"
      }
    ],
    "station_status": "Available",
    "is_under_maintenance": false,
    "timestamp": "2025-01-29T12:00:00Z"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

**Status Values:**
- `available`: Station has available connectors (green icon, shows X/Y)
- `in_use`: All connectors are in use (blue icon, no number)
- `unavailable`: Station under maintenance or all connectors unavailable (red icon, no number)

**Example: All Connectors In Use**
```json
{
  "type": "charger_status_update",
  "station_id": "STATION001",
  "charger_id": "CP001",
  "status": "in_use",
  "data": {
    "total_connectors": 4,
    "available_connectors": 0,
    "connectors_in_use": 4,
    "connectors_unavailable": 0,
    "display": null,
    "connector_status": [
      {
        "connector_id": 1,
        "status": "Charging"
      },
      {
        "connector_id": 2,
        "status": "Charging"
      },
      {
        "connector_id": 3,
        "status": "Charging"
      },
      {
        "connector_id": 4,
        "status": "Charging"
      }
    ],
    "station_status": "In Use",
    "is_under_maintenance": false,
    "timestamp": "2025-01-29T12:00:00Z"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

**Example: Under Maintenance**
```json
{
  "type": "charger_status_update",
  "station_id": "STATION001",
  "charger_id": "CP001",
  "status": "unavailable",
  "data": {
    "total_connectors": 4,
    "available_connectors": 0,
    "connectors_in_use": 0,
    "connectors_unavailable": 4,
    "display": null,
    "connector_status": [
      {
        "connector_id": 1,
        "status": "Unavailable"
      },
      {
        "connector_id": 2,
        "status": "Unavailable"
      },
      {
        "connector_id": 3,
        "status": "Unavailable"
      },
      {
        "connector_id": 4,
        "status": "Unavailable"
      }
    ],
    "station_status": "Unavailable",
    "is_under_maintenance": true,
    "maintenance_reason": "Scheduled maintenance",
    "timestamp": "2025-01-29T12:00:00Z"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

#### 4.7 Charger List Update (Pushed from Gateway)

**Type:** `charger_list_update`

**Purpose:** Automatically pushed to mobile clients when charger list needs to be updated (e.g., new charger added, charger removed, or initial load).

**Message:**
```json
{
  "type": "charger_list_update",
  "action": "update",
  "data": {
    "chargers": [
      {
        "station_id": "STATION001",
        "station_name": "Main Street Station",
        "location": {
          "latitude": 40.7128,
          "longitude": -74.0060,
          "address": "123 Main Street"
        },
        "chargers": [
          {
            "charger_id": "CP001",
            "total_connectors": 4,
            "available_connectors": 3,
            "status": "available",
            "display": "3/4"
          },
          {
            "charger_id": "CP002",
            "total_connectors": 2,
            "available_connectors": 0,
            "status": "in_use",
            "display": null
          }
        ],
        "station_status": "available",
        "total_connectors": 6,
        "available_connectors": 3,
        "display": "3/6"
      }
    ],
    "timestamp": "2025-01-29T12:00:00Z"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

#### 4.8 Active Session Update (Pushed from Gateway)

**Type:** `active_session_update`

**Purpose:** Automatically pushed to mobile clients when their active session status changes.

**Message:**
```json
{
  "type": "active_session_update",
  "has_active_session": true,
  "data": {
    "session_id": 456,
    "transaction_id": 789,
    "charger_id": "CP001",
    "connector_id": 1,
    "station_id": "STATION001",
    "start_time": "2025-01-29T12:00:00Z",
    "energy_delivered": 5.5,
    "duration": 3600,
    "status": "active"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

**No Active Session:**
```json
{
  "type": "active_session_update",
  "has_active_session": false,
  "data": null,
  "timestamp": "2025-01-29T12:00:00Z"
}
```

#### 4.9 Error Message

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

**1. Mobile App → Laravel Backend (REST API):**
```http
POST /api/charging/start HTTP/1.1
Authorization: Bearer {token}
Content-Type: application/json

{
  "charger_id": "CP001",
  "connector_id": 1
}
```

**2. Laravel Backend → Python CMS (REST API):**
```http
POST /api/charging/remote_start HTTP/1.1
Host: python-cms.com
Content-Type: application/json

{
  "charger_id": "CP001",
  "id_tag": "RFID123",
  "connector_id": 1
}
```

**3. Laravel Backend → Mobile App (REST API Response):**
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

**4. Laravel Backend → Redis (Publish):**
```php
// Published to: user:123:session_updates
Redis::publish("user:123:session_updates", json_encode([
    'type' => 'session_update',
    'session_id' => 456,
    'transaction_id' => 789,
    'event' => 'session_started',
    'data' => [
        'charger_id' => 'CP001',
        'connector_id' => 1,
        'id_tag' => 'RFID123',
        'meter_start' => 1000,
        'start_time' => now()->toIso8601String()
    ],
    'timestamp' => now()->toIso8601String()
]));
```

**5. Node.js Gateway → Mobile App (WebSocket - Auto-pushed):**
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

### Example 2: Real-time Meter Value Updates

**1. Python CMS → Laravel Backend (via internal event):**
```json
{
  "event": "meter_value",
  "charger_id": "CP001",
  "transaction_id": 789,
  "data": {
    "energy_delivered": 42.5,
    "power": 22.0,
    "voltage": 230,
    "current": 95.7,
    "meter_value": 42500,
    "charge_percentage": 50,
    "time_remaining": 1200
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
        'station_id' => 'STATION001',
        'station_name' => 'Cillout Mansoura',
        'station_address' => '15 Tahrir Street, Downtown, Cairo',
        'charge_percentage' => 50,
        'time_remaining' => 1200,
        'time_remaining_display' => '20 min',
        'energy_consumed' => 42.5,
        'energy_consumed_unit' => 'kWh',
        'cost' => 315,
        'cost_currency' => 'EGP',
        'charging_duration' => 8100,
        'charging_duration_display' => '2hr 15min',
        'output_power' => 22.0,
        'output_power_unit' => 'kW',
        'energy_delivered' => 42.5,
        'power' => 22.0,
        'voltage' => 230,
        'current' => 95.7,
        'meter_value' => 42500,
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
    "station_id": "STATION001",
    "station_name": "Cillout Mansoura",
    "station_address": "15 Tahrir Street, Downtown, Cairo",
    "charge_percentage": 50,
    "time_remaining": 1200,
    "time_remaining_display": "20 min",
    "energy_consumed": 42.5,
    "energy_consumed_unit": "kWh",
    "cost": 315,
    "cost_currency": "EGP",
    "charging_duration": 8100,
    "charging_duration_display": "2hr 15min",
    "output_power": 22.0,
    "output_power_unit": "kW",
    "energy_delivered": 42.5,
    "power": 22.0,
    "voltage": 230,
    "current": 95.7,
    "meter_value": 42500,
    "timestamp": "2025-01-29T12:05:00Z"
  },
  "timestamp": "2025-01-29T12:05:00Z"
}
```

### Example 3: Charger Status Update (Pushed to Mobile)

**1. Charger Status Changes (e.g., connector becomes available):**
- Status change detected by Python CMS or Laravel backend
- Triggered by OCPP StatusNotification message or manual status change

**2. Laravel Backend → Redis (Publish):**
```php
// Published to: user:123:charger_updates (broadcasted to all connected users)
Redis::publish("user:123:charger_updates", json_encode([
    'type' => 'charger_status_update',
    'station_id' => 'STATION001',
    'charger_id' => 'CP001',
    'status' => 'available',
    'data' => [
        'total_connectors' => 4,
        'available_connectors' => 3,
        'connectors_in_use' => 1,
        'connectors_unavailable' => 0,
        'display' => '3/4',
        'connector_status' => [
            ['connector_id' => 1, 'status' => 'Available'],
            ['connector_id' => 2, 'status' => 'Available'],
            ['connector_id' => 3, 'status' => 'Available'],
            ['connector_id' => 4, 'status' => 'Charging']
        ],
        'station_status' => 'Available',
        'is_under_maintenance' => false,
        'timestamp' => now()->toIso8601String()
    ],
    'timestamp' => now()->toIso8601String()
]));
```

**3. Node.js Gateway → Mobile App (WebSocket):**
```json
{
  "type": "charger_status_update",
  "station_id": "STATION001",
  "charger_id": "CP001",
  "status": "available",
  "data": {
    "total_connectors": 4,
    "available_connectors": 3,
    "connectors_in_use": 1,
    "connectors_unavailable": 0,
    "display": "3/4",
    "connector_status": [
      {
        "connector_id": 1,
        "status": "Available"
      },
      {
        "connector_id": 2,
        "status": "Available"
      },
      {
        "connector_id": 3,
        "status": "Available"
      },
      {
        "connector_id": 4,
        "status": "Charging"
      }
    ],
    "station_status": "Available",
    "is_under_maintenance": false,
    "timestamp": "2025-01-29T12:00:00Z"
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

**4. Mobile App Updates Map:**
- Updates the charging station icon on the map
- Shows green icon with "3/4" displayed below it
- No user action required - update is automatic

### Example 4: Stop Charging Flow

**1. Mobile App → Laravel Backend (REST API):**
```http
POST /api/charging/stop HTTP/1.1
Authorization: Bearer {token}
Content-Type: application/json

{
  "charger_id": "CP001"
}
```

**2. Laravel Backend → Python CMS (REST API):**
```http
POST /api/charging/stop HTTP/1.1
Host: python-cms.com
Content-Type: application/json

{
  "charger_id": "CP001"
}
```

**3. Laravel Backend → Mobile App (REST API Response):**
```json
{
  "success": true,
  "data": {
    "session_id": 456,
    "transaction_id": 789,
    "status": "stopped",
    "energy_delivered": 14.5,
    "duration": 3600,
    "message": "Charging session stopped"
  }
}
```

**4. Laravel Backend → Redis (Publish):**
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

**5. Node.js Gateway → Mobile App (WebSocket - Auto-pushed):**
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

---

## Redis Channel Summary

| Channel Pattern | Purpose | Message Type | Pushed To |
|----------------|---------|--------------|-----------|
| `user:{userId}:notifications` | General notifications | `notification` | All connected mobile clients |
| `user:{userId}:session_updates` | Charging session updates | `session_update` | All connected mobile clients |
| `user:{userId}:charger_updates` | Charger status updates | `charger_status_update` | All connected mobile clients |

**Note:** Charger status updates are automatically pushed to all connected mobile clients to update the map display in real-time. Mobile apps should NOT request charger status - it is pushed automatically when status changes occur.

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

1. **Use REST API for commands** - Always use REST API for start/stop charging operations
2. **WebSocket is receive-only** - Do NOT send commands via WebSocket, only receive updates
3. **Always handle connection errors** - Implement reconnection logic for WebSocket
4. **Handle all message types** - Listen for charger updates, session updates, and notifications
5. **Use proper error handling** - Display user-friendly error messages from REST API responses
6. **Implement reconnection** - Handle network interruptions gracefully for WebSocket
7. **Update UI immediately** - Update map and UI elements when receiving WebSocket updates
8. **Separate concerns** - Use REST API for user actions, WebSocket for real-time updates

---

## Testing

### Using wscat

```bash
wscat -c "ws://localhost:8080?token=YOUR_TOKEN"
```

### Using JavaScript

```javascript
// 1. Connect to WebSocket for real-time updates (receive-only)
const ws = new WebSocket('ws://localhost:8080?token=YOUR_TOKEN');

ws.onopen = () => {
  console.log('WebSocket connected - ready to receive real-time updates');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Received update:', message);
  
  // Handle different message types
  switch(message.type) {
    case 'connected':
      console.log('Connection confirmed');
      break;
    case 'charger_status_update':
      // Automatically pushed charger status update
      // Update map icon: Green (X/Y), Blue (no number), Red (no number)
      updateMapIcon(message);
      break;
    case 'session_update':
      // Real-time session updates (meter values, etc.)
      updateSessionDisplay(message);
      break;
    case 'active_session_update':
      // Active session status pushed automatically
      updateActiveSessionDisplay(message);
      break;
    case 'charger_list_update':
      // Charger list pushed automatically
      updateChargerList(message);
      break;
    case 'notification':
      // General notifications
      showNotification(message);
      break;
    case 'error':
      console.error('Error:', message.message);
      break;
  }
};

// 2. Use REST API for start/stop charging (NOT WebSocket)
async function startCharging(chargerId, connectorId = 1) {
  try {
    const response = await fetch('https://laravel-backend.com/api/charging/start', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        charger_id: chargerId,
        connector_id: connectorId
      })
    });
    
    const result = await response.json();
    
    if (result.success) {
      console.log('Charging started:', result.data);
      // Real-time updates will come via WebSocket automatically
    } else {
      console.error('Failed to start charging:', result.error);
    }
  } catch (error) {
    console.error('Error starting charging:', error);
  }
}

async function stopCharging(chargerId = null) {
  try {
    const response = await fetch('https://laravel-backend.com/api/charging/stop', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        charger_id: chargerId // Optional - if null, stops active session
      })
    });
    
    const result = await response.json();
    
    if (result.success) {
      console.log('Charging stopped:', result.data);
      // Real-time updates will come via WebSocket automatically
    } else {
      console.error('Failed to stop charging:', result.error);
    }
  } catch (error) {
    console.error('Error stopping charging:', error);
  }
}

function updateMapIcon(message) {
  // Update charging station icon on map
  const { status, data } = message;
  
  if (status === 'available') {
    // Green icon with X/Y display (e.g., "3/4")
    showGreenIcon(message.station_id, data.display);
  } else if (status === 'in_use') {
    // Blue icon, no number
    showBlueIcon(message.station_id);
  } else if (status === 'unavailable') {
    // Red icon, no number
    showRedIcon(message.station_id);
  }
}
```

---

*Last Updated: 2025-01-29*

