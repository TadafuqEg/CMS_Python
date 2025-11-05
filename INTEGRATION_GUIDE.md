# Complete Integration Guide

## Overview

This guide explains how to integrate the Node.js WebSocket Gateway with Laravel backend and Python CMS.

## Architecture Flow

```
Mobile App → Node.js Gateway → Laravel API → Python CMS → Chargers
              ↓                    ↓
           Redis Pub/Sub       Redis Pub/Sub
```

## Setup Instructions

### 1. Node.js Gateway Setup

#### Install Dependencies

```bash
cd nodejs-gateway
npm install
```

#### Configure Environment

Create `.env` file:

```env
# Server Configuration
PORT=8080
NODE_ENV=production
INSTANCE_ID=gateway-1

# Laravel Backend API
LARAVEL_API_URL=http://localhost:8000
LARAVEL_API_TIMEOUT=5000

# JWT Configuration
JWT_SECRET=your-jwt-secret-key-here
JWT_ALGORITHM=HS256
JWT_ISSUER=laravel-backend

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# Connection Limits
MAX_CONNECTIONS_PER_INSTANCE=10000
HEARTBEAT_INTERVAL=30000
CONNECTION_TIMEOUT=60000

# Cluster Mode
CLUSTER_MODE=false
CLUSTER_WORKERS=4

# Logging
LOG_LEVEL=info
LOG_FILE=logs/gateway.log
```

#### Start Server

```bash
# Development
npm run dev

# Production
npm start

# Cluster Mode
npm run cluster
```

### 2. Laravel Backend Setup

#### Copy Files

Copy all files from `laravel-integration/` to your Laravel project:

- `app/Services/ChargingService.php`
- `app/Http/Controllers/ChargingController.php`
- `app/Http/Controllers/WebSocketController.php`
- `app/Listeners/ChargerStatusListener.php`
- Update `routes/api.php`
- Update `config/services.php`

#### Configure Environment

Add to Laravel `.env`:

```env
PYTHON_CMS_URL=http://localhost:8001
PYTHON_CMS_TIMEOUT=10
```

#### Database Migrations

Create `charging_sessions` table:

```php
Schema::create('charging_sessions', function (Blueprint $table) {
    $table->id();
    $table->unsignedBigInteger('user_id');
    $table->string('charger_id');
    $table->integer('connector_id')->default(1);
    $table->string('status')->default('active'); // active, stopped, completed
    $table->timestamp('started_at');
    $table->timestamp('stopped_at')->nullable();
    $table->string('python_cms_message_id')->nullable();
    $table->timestamps();
    
    $table->foreign('user_id')->references('id')->on('users');
    $table->index(['user_id', 'status']);
    $table->index('charger_id');
});
```

### 3. Python CMS Updates

#### Add Event Publishing to Redis

Update your Python CMS to publish events to Redis when charger events occur:

```python
# In app/services/ocpp_handler.py or similar

import redis
import json

redis_client = redis.Redis(
    host='localhost',
    port=6379,
    db=0
)

async def publish_charger_event(event_type, charger_id, data):
    """Publish charger event to Redis"""
    event = {
        'event': event_type,
        'charger_id': charger_id,
        'data': data,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    # Publish to charger-specific channel
    redis_client.publish(f'charger:{charger_id}:events', json.dumps(event))
    
    # Publish to general charger events channel
    redis_client.publish('charger:events', json.dumps(event))

# Example: When charger status changes
async def handle_status_notification(charger_id, status):
    await publish_charger_event('status_notification', charger_id, {
        'status': status
    })

# Example: When session starts
async def handle_start_transaction(charger_id, transaction_id):
    await publish_charger_event('session_started', charger_id, {
        'transaction_id': transaction_id
    })
```

## Usage Examples

### Mobile App Connection

```javascript
// Connect to WebSocket gateway
const token = 'your-jwt-token-from-laravel';
const ws = new WebSocket(`wss://your-domain.com:8080?token=${token}`);

ws.onopen = () => {
  console.log('Connected to gateway');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Received:', message);
};

// Send message to start charging
ws.send(JSON.stringify({
  action: 'start_charging',
  data: {
    charger_id: 'CP001',
    connector_id: 1
  }
}));
```

### Laravel API Usage

```php
// In your Laravel controller or service
use App\Services\ChargingService;

$chargingService = app(ChargingService::class);

// Start charging
$result = $chargingService->startCharging($user, 'CP001', 1);

// Stop charging
$result = $chargingService->stopCharging($user);

// Get charger status
$status = $chargingService->getChargerStatus('CP001');
```

### Python CMS API Calls

The Laravel service automatically calls Python CMS APIs:

```php
// ChargingService.php automatically calls:
// POST http://python-cms:8001/api/charging/remote_start
// POST http://python-cms:8001/api/charging/remote_stop
// GET http://python-cms:8001/api/chargers/{id}/status
```

## Real-time Updates Flow

### Example: Charger Status Update

1. **Charger sends StatusNotification** → Python CMS
2. **Python CMS publishes to Redis:**
   ```json
   {
     "event": "status_notification",
     "charger_id": "CP001",
     "status": "Charging",
     "timestamp": "2025-01-29T12:00:00Z"
   }
   ```

3. **Laravel subscribes to Redis** (via ChargerStatusListener)
4. **Laravel finds active sessions** on this charger
5. **Laravel publishes to user channels:**
   ```json
   {
     "type": "charger_status_changed",
     "charger_id": "CP001",
     "status": "Charging",
     "user_id": 123
   }
   ```

6. **Node.js Gateway receives** from Redis
7. **Node.js Gateway forwards** to connected mobile app
8. **Mobile app receives** real-time update

## Testing

### Test Node.js Gateway

```bash
cd nodejs-gateway
node test/load-test.js
```

### Test Laravel Integration

```bash
# Test API endpoints
curl -X POST http://localhost:8000/api/charging/start \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"charger_id": "CP001"}'
```

### Test WebSocket Connection

```javascript
// Use browser console or Node.js script
const ws = new WebSocket('ws://localhost:8080?token=YOUR_TOKEN');
ws.onopen = () => console.log('Connected');
ws.onmessage = (e) => console.log('Message:', e.data);
```

## Monitoring

### Node.js Gateway Health

```bash
curl http://localhost:8080/health
curl http://localhost:8080/stats
```

### Laravel Logs

```bash
tail -f storage/logs/laravel.log
```

### Redis Monitoring

```bash
redis-cli MONITOR
```

## Troubleshooting

### Connection Issues

1. Check JWT token is valid
2. Verify Laravel API is accessible
3. Check Redis connection
4. Review logs for errors

### Performance Issues

1. Check connection limits
2. Monitor Redis pub/sub performance
3. Scale horizontally (add more instances)
4. Check network latency

### Missing Updates

1. Verify Redis pub/sub is working
2. Check Laravel listener is running
3. Verify user channels are subscribed
4. Check Python CMS is publishing events

## Production Deployment

### Load Balancer Configuration

```nginx
# Nginx configuration for Node.js gateway
upstream websocket_gateway {
    least_conn;
    server gateway1:8080;
    server gateway2:8080;
    server gateway3:8080;
}

server {
    listen 443 ssl;
    server_name ws.yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://websocket_gateway;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

### Scaling Strategy

1. **Start with 1 Node.js gateway instance** (10K connections)
2. **Add instances as needed** (10-20 instances for 100K)
3. **Use load balancer** to distribute connections
4. **Monitor connection counts** and scale accordingly

## Security Considerations

1. **JWT tokens** - Use strong secrets, validate on every request
2. **TLS/SSL** - Always use WSS (secure WebSocket)
3. **Rate limiting** - Implement per-user rate limits
4. **Input validation** - Validate all inputs from mobile apps
5. **Error handling** - Don't expose sensitive information in errors

## Next Steps

1. Implement authentication and authorization
2. Add rate limiting
3. Set up monitoring and alerting
4. Configure auto-scaling
5. Implement retry logic
6. Add circuit breakers for external services

---

*Last Updated: 2025-01-29*


