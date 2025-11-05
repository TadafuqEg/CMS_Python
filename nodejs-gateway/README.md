# Node.js WebSocket Gateway

High-performance WebSocket gateway for handling 100K+ concurrent mobile app connections.

## Features

- ✅ High-performance WebSocket handling (10K+ connections per instance)
- ✅ JWT authentication with Laravel backend
- ✅ Redis pub/sub for real-time notifications
- ✅ Cluster mode support for horizontal scaling
- ✅ Connection management and heartbeat
- ✅ Health checks and statistics
- ✅ Graceful shutdown
- ✅ Comprehensive logging

## Installation

```bash
npm install
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Key configuration:
- `PORT`: WebSocket server port (default: 8080)
- `LARAVEL_API_URL`: Laravel backend API URL
- `JWT_SECRET`: JWT secret key (must match Laravel)
- `REDIS_HOST`: Redis server host
- `MAX_CONNECTIONS_PER_INSTANCE`: Max connections per instance (default: 10000)

## Usage

### Development Mode

```bash
npm run dev
```

### Production Mode

```bash
npm start
```

### Cluster Mode (Multiple Workers)

```bash
npm run cluster
```

Or set `CLUSTER_MODE=true` in `.env`

## API Endpoints

### Health Check
```
GET /health
```

### Statistics
```
GET /stats
```

## WebSocket Connection

Connect to WebSocket server with JWT token:

```
wss://your-domain.com:8080?token=your-jwt-token
```

## Message Format

### Client → Server

```json
{
  "action": "start_charging",
  "data": {
    "charger_id": "CP001"
  }
}
```

### Server → Client

```json
{
  "type": "response",
  "action": "start_charging",
  "data": {
    "status": "success",
    "transaction_id": 123
  },
  "timestamp": "2025-01-29T12:00:00Z"
}
```

## Testing

Load testing script:

```bash
node test/load-test.js
```

## Monitoring

- Check `/health` endpoint for server status
- Check `/stats` endpoint for connection statistics
- Logs are written to `logs/gateway.log`

## Scaling

For 100K connections:
1. Run 10-20 instances behind a load balancer
2. Each instance handles 5K-10K connections
3. Use Redis for pub/sub coordination
4. Use cluster mode for better CPU utilization

## Production Deployment

1. Use PM2 or Kubernetes for process management
2. Set up load balancer (HAProxy/Nginx)
3. Configure Redis cluster
4. Enable monitoring and alerting
5. Set up log aggregation


