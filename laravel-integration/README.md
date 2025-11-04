# Laravel Integration with Python CMS

This package provides Laravel services and controllers for integrating with the Python CMS (Central Management System) for EV charging operations.

## Installation

1. Copy the service classes to `app/Services/`
2. Copy the controllers to `app/Http/Controllers/`
3. Copy the routes to `routes/api.php`
4. Update `config/services.php` with Python CMS configuration

## Configuration

Add to `.env`:

```env
PYTHON_CMS_URL=http://localhost:8001
PYTHON_CMS_TIMEOUT=10
```

## Services

### ChargingService

Main service for handling charging operations:

- `startCharging()` - Start a charging session
- `stopCharging()` - Stop a charging session
- `getChargerStatus()` - Get charger status
- `getActiveSession()` - Get active session for user
- `listAvailableChargers()` - List available chargers
- `handleWebSocketMessage()` - Handle messages from Node.js gateway

## Controllers

### ChargingController

REST API endpoints for charging operations:

- `POST /api/charging/start` - Start charging
- `POST /api/charging/stop` - Stop charging
- `GET /api/charging/session/active` - Get active session
- `GET /api/charging/charger/{id}/status` - Get charger status
- `GET /api/charging/chargers` - List chargers

### WebSocketController

Handles WebSocket messages from Node.js gateway:

- `POST /api/websocket/message` - Handle WebSocket messages
- `POST /api/auth/validate-token` - Validate JWT tokens

## Usage Examples

### Start Charging Session

```php
$chargingService = app(ChargingService::class);
$result = $chargingService->startCharging($user, 'CP001', 1);
```

### Handle WebSocket Message

```php
// In WebSocketController
$result = $chargingService->handleWebSocketMessage(
    $user,
    'start_charging',
    ['charger_id' => 'CP001']
);
```

## Real-time Updates

The service publishes notifications to Redis channels:
- `user:{userId}:notifications` - General notifications
- `user:{userId}:session_updates` - Session updates
- `user:{userId}:charger_updates` - Charger status updates

The Node.js gateway subscribes to these channels and forwards messages to connected mobile apps.

## Error Handling

All methods throw exceptions that should be caught and handled appropriately. The controllers return JSON responses with error details.

## Logging

All operations are logged using Laravel's logging system. Check `storage/logs/laravel.log` for details.

## Testing

```bash
php artisan test --filter ChargingServiceTest
```

