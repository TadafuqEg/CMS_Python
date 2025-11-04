# Scalability Architecture for 100K Mobile App Clients

## Current System Analysis

### Current Stack:
- **Python FastAPI CMS** - OCPP protocol handler for EV chargers
- **PHP Laravel** - Business logic backend
- **Mobile Apps** - Need real-time updates (100K concurrent clients expected)

### Current CMS Capabilities:
- OCPP WebSocket connections for chargers (specialized protocol)
- REST API for management operations
- Real-time session management
- Database operations (SQLite/PostgreSQL)

---

## Architecture Options Analysis

### Option 1: Direct Mobile → PHP Laravel (with WebSocket)
**Pros:**
- ✅ Single backend for business logic
- ✅ Laravel has good WebSocket support (Laravel Echo, Pusher, Soketi)
- ✅ Centralized authentication/authorization
- ✅ Easier to maintain and debug
- ✅ Can use Redis for pub/sub and scaling

**Cons:**
- ⚠️ PHP not optimized for high-concurrency WebSocket connections
- ⚠️ Each Laravel worker can handle ~1K-2K connections max
- ⚠️ Requires horizontal scaling (many Laravel instances)
- ⚠️ Higher resource consumption per connection

**Scalability:**
- Need 50-100 Laravel workers for 100K connections
- Requires load balancer (HAProxy/Nginx)
- Redis for pub/sub coordination

---

### Option 2: Direct Mobile → Python CMS
**Pros:**
- ✅ Python asyncio handles WebSocket well
- ✅ Single system for everything
- ✅ Direct access to OCPP data

**Cons:**
- ❌ Mixes business logic with OCPP protocol handling
- ❌ Couples mobile app logic to charger infrastructure
- ❌ Harder to maintain and scale separately
- ❌ Security concerns (OCPP endpoints exposed)

**Verdict:** ❌ **NOT RECOMMENDED** - Mixes concerns

---

### Option 3: Mobile → Node.js Gateway → PHP Laravel → Python CMS (RECOMMENDED)
**Pros:**
- ✅ **Best performance** - Node.js handles 100K+ WebSocket connections efficiently
- ✅ **Separation of concerns** - Each layer has specific purpose
- ✅ **Scalability** - Node.js can handle 10K+ connections per instance
- ✅ **Business logic isolation** - Laravel handles auth, payments, user management
- ✅ **OCPP isolation** - Python CMS only handles charger communication
- ✅ **Independent scaling** - Scale each layer based on load

**Cons:**
- ⚠️ More complex architecture (3 layers)
- ⚠️ Requires message queue/bus for inter-service communication
- ⚠️ Need to handle service failures gracefully

**Scalability:**
- 10-20 Node.js instances for 100K connections (5K-10K per instance)
- 5-10 Laravel workers for business logic
- 2-5 Python CMS instances for charger communication

---

## Recommended Architecture (Option 3)

```
┌─────────────────────────────────────────────────────────────┐
│                    Mobile Applications                       │
│                    (100K Concurrent Users)                   │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        │ WebSocket (wss://)
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ▼                               ▼
┌──────────────────┐         ┌──────────────────┐
│  Node.js Gateway │         │  Node.js Gateway │
│  (WS Handler)    │         │  (WS Handler)    │
│  Instance 1      │         │  Instance N      │
│  10K connections │         │  10K connections │
└────────┬─────────┘         └────────┬─────────┘
         │                            │
         └────────────┬───────────────┘
                      │
                      │ HTTP REST API / Redis Pub/Sub
                      │
         ┌────────────┴────────────┐
         │                         │
         ▼                         ▼
┌──────────────────┐      ┌──────────────────┐
│  PHP Laravel     │      │  PHP Laravel     │
│  (Business Logic)│      │  (Business Logic)│
│  Instance 1      │      │  Instance N      │
└────────┬─────────┘      └────────┬─────────┘
         │                         │
         └────────────┬────────────┘
                      │
                      │ HTTP REST API / Message Queue (Redis/RabbitMQ)
                      │
         ┌────────────┴────────────┐
         │                         │
         ▼                         ▼
┌──────────────────┐      ┌──────────────────┐
│  Python CMS      │      │  Python CMS      │
│  (OCPP Handler)  │      │  (OCPP Handler)  │
│  Instance 1      │      │  Instance N      │
└────────┬─────────┘      └────────┬─────────┘
         │                         │
         └────────────┬────────────┘
                      │
                      │ OCPP WebSocket (wss://)
                      │
         ┌────────────┴────────────┐
         │                         │
         ▼                         ▼
              EV Charging Stations
```

---

## Detailed Layer Breakdown

### 1. Node.js WebSocket Gateway Layer

**Purpose:** Handle high-concurrency WebSocket connections from mobile apps

**Technology Stack:**
- **Node.js** with `ws` or `socket.io` library
- **Redis** for pub/sub and session management
- **Load Balancer** (HAProxy/Nginx) for connection distribution

**Key Features:**
- Authentication token validation (JWT from Laravel)
- Connection management and heartbeat
- Message routing to Laravel backend
- Broadcast capabilities via Redis pub/sub
- Connection scaling (horizontal)

**Example Structure:**
```javascript
// ws-gateway/server.js
const WebSocket = require('ws');
const Redis = require('ioredis');
const jwt = require('jsonwebtoken');

const redis = new Redis();
const wss = new WebSocket.Server({ port: 8080 });

wss.on('connection', async (ws, req) => {
  // Validate JWT token
  const token = extractToken(req);
  const user = await validateWithLaravel(token);
  
  // Store connection
  await redis.set(`ws:${user.id}`, ws.id);
  
  // Subscribe to user-specific channels
  await redis.subscribe(`user:${user.id}:notifications`);
  
  // Handle messages
  ws.on('message', async (message) => {
    await forwardToLaravel(user.id, message);
  });
  
  // Handle Redis pub/sub
  redis.on('message', (channel, message) => {
    if (channel === `user:${user.id}:notifications`) {
      ws.send(message);
    }
  });
});
```

**Scaling:**
- Each Node.js instance: 5K-10K connections
- Use PM2 cluster mode or Kubernetes
- Load balancer distributes connections

---

### 2. PHP Laravel Backend Layer

**Purpose:** Business logic, authentication, data management

**Key Responsibilities:**
- User authentication/authorization (JWT)
- Payment processing
- User management
- Business rules and validation
- Database operations
- Push notifications coordination

**API Endpoints:**
- `POST /api/auth/login` - Authentication
- `GET /api/chargers` - List chargers
- `POST /api/sessions/start` - Start charging session
- `POST /api/sessions/stop` - Stop charging session
- `GET /api/sessions/status` - Get session status

**Integration with Python CMS:**
```php
// Laravel Service
class ChargingService {
    public function startCharging($userId, $chargerId) {
        // Business logic validation
        $user = User::find($userId);
        if (!$user->hasActiveSubscription()) {
            throw new Exception('No active subscription');
        }
        
        // Call Python CMS API
        $response = Http::post('http://python-cms:8000/api/charging/remote_start', [
            'charger_id' => $chargerId,
            'id_tag' => $user->id_tag,
            'connector_id' => 1
        ]);
        
        // Publish to Redis for real-time updates
        Redis::publish("user:{$userId}:notifications", json_encode([
            'type' => 'session_started',
            'data' => $response->json()
        ]));
        
        return $response->json();
    }
}
```

---

### 3. Python CMS Layer (Current System)

**Purpose:** OCPP protocol handling for EV chargers

**Key Responsibilities:**
- OCPP WebSocket connections from chargers
- Charger management
- Session tracking
- Real-time charger status
- OCPP command execution

**API Endpoints (for Laravel):**
- `POST /api/charging/remote_start` - Start charging
- `POST /api/charging/remote_stop` - Stop charging
- `GET /api/chargers/{id}/status` - Get charger status
- `GET /api/sessions/{id}` - Get session details

**Webhook/Event Publishing:**
- Publish events to Redis/RabbitMQ when charger events occur
- Laravel subscribes to these events and pushes to mobile apps via Node.js gateway

---

## Communication Flow Examples

### Example 1: User Starts Charging Session

```
1. Mobile App → Node.js Gateway (WebSocket)
   {"action": "start_charging", "charger_id": "CP001", "token": "jwt..."}

2. Node.js Gateway → PHP Laravel (HTTP)
   POST /api/sessions/start
   Headers: Authorization: Bearer {jwt}

3. PHP Laravel:
   - Validates user & permissions
   - Checks subscription status
   - Calls Python CMS API

4. PHP Laravel → Python CMS (HTTP)
   POST /api/charging/remote_start
   {"charger_id": "CP001", "id_tag": "USER123", "connector_id": 1}

5. Python CMS:
   - Sends OCPP RemoteStartTransaction to charger
   - Waits for StartTransaction response
   - Creates session in database

6. Python CMS → Redis (Pub/Sub)
   Publishes: {"event": "session_started", "charger_id": "CP001", "transaction_id": 123}

7. PHP Laravel (Redis Subscriber):
   - Receives event
   - Updates user session in database
   - Publishes to user channel

8. Redis → Node.js Gateway (Pub/Sub)
   Channel: user:123:notifications
   Message: {"type": "session_started", "data": {...}}

9. Node.js Gateway → Mobile App (WebSocket)
   Sends notification to connected user's WebSocket
```

### Example 2: Real-time Charger Status Update

```
1. Charger → Python CMS (OCPP WebSocket)
   StatusNotification: {"status": "Charging", "connector_id": 1}

2. Python CMS:
   - Updates database
   - Publishes to Redis

3. Redis → PHP Laravel (Pub/Sub)
   Event: {"event": "charger_status_changed", "charger_id": "CP001", "status": "Charging"}

4. PHP Laravel:
   - Finds all users with active sessions on this charger
   - Publishes to user channels

5. Redis → Node.js Gateway (Pub/Sub)
   Multiple channels: user:123:notifications, user:456:notifications

6. Node.js Gateway → Mobile Apps (WebSocket)
   Sends to all connected users with active sessions
```

---

## Technology Stack Recommendations

### Node.js Gateway
- **Runtime:** Node.js 18+ LTS
- **WebSocket Library:** `ws` (lightweight) or `socket.io` (feature-rich)
- **Process Manager:** PM2 cluster mode or Kubernetes
- **Load Balancer:** HAProxy or Nginx
- **Session Store:** Redis

### PHP Laravel
- **Version:** Laravel 10+
- **Queue:** Redis Queue or RabbitMQ
- **Cache:** Redis
- **HTTP Client:** Guzzle for Python CMS API calls
- **WebSocket:** Laravel Echo Server (optional) or rely on Node.js gateway

### Python CMS
- **Framework:** FastAPI (current)
- **Message Queue:** Redis Pub/Sub or RabbitMQ
- **Database:** PostgreSQL (for production, not SQLite)
- **WebSocket:** websockets library (current)

### Infrastructure
- **Load Balancer:** HAProxy or AWS ALB
- **Message Queue:** Redis Pub/Sub or RabbitMQ
- **Database:** PostgreSQL (shared between Laravel and Python CMS)
- **Cache:** Redis
- **Monitoring:** Prometheus + Grafana
- **Logging:** ELK Stack or CloudWatch

---

## Scaling Estimates for 100K Concurrent Users

### Node.js Gateway Layer
- **Instances:** 10-20 instances
- **Connections per instance:** 5K-10K
- **Resources:** 2 CPU cores, 4GB RAM per instance
- **Total:** ~20-40 CPU cores, 40-80GB RAM

### PHP Laravel Layer
- **Instances:** 5-10 instances
- **Workers per instance:** 4-8 workers
- **Resources:** 4 CPU cores, 8GB RAM per instance
- **Total:** ~20-40 CPU cores, 40-80GB RAM

### Python CMS Layer
- **Instances:** 2-5 instances (depends on charger count, not mobile users)
- **Resources:** 4 CPU cores, 8GB RAM per instance
- **Total:** ~8-20 CPU cores, 16-40GB RAM

### Supporting Infrastructure
- **Redis:** 3-node cluster (16GB each)
- **PostgreSQL:** Primary + 2 replicas (32GB each)
- **Load Balancer:** 2 instances (HA)

**Total Infrastructure Estimate:**
- **CPU Cores:** 50-100 cores
- **RAM:** 150-250 GB
- **Cost (AWS):** ~$2,000-4,000/month (on-demand)
- **Cost (Reserved):** ~$1,000-2,000/month

---

## Implementation Phases

### Phase 1: Node.js Gateway (MVP)
**Duration:** 2-3 weeks
- Basic WebSocket server with authentication
- Connection management
- Message forwarding to Laravel
- Redis pub/sub for notifications
- Load testing (1K → 10K → 50K connections)

### Phase 2: Laravel Integration
**Duration:** 2-3 weeks
- API endpoints for mobile app
- JWT authentication
- Integration with Python CMS
- Redis pub/sub subscriber
- Error handling and retries

### Phase 3: Python CMS Updates
**Duration:** 1-2 weeks
- Event publishing to Redis
- Webhook endpoints for Laravel
- Rate limiting and security
- Health checks

### Phase 4: Production Hardening
**Duration:** 2-3 weeks
- Load balancing setup
- Monitoring and alerting
- Auto-scaling configuration
- Disaster recovery
- Performance optimization

**Total Timeline:** 7-11 weeks

---

## Alternative: Hybrid Approach (Phased)

If you want to start simpler and scale gradually:

### Phase 1: Direct Mobile → Laravel (with Laravel Echo/Soketi)
- Start with Laravel Echo Server (Soketi - Node.js based)
- Handle 10K-20K connections initially
- Simpler architecture, faster to implement

### Phase 2: Add Dedicated Node.js Gateway
- When you reach 20K+ connections
- Migrate gradually
- Both systems can coexist during transition

### Phase 3: Full Architecture
- Scale to 100K+ connections
- Optimize and fine-tune

---

## Security Considerations

1. **Authentication:**
   - JWT tokens issued by Laravel
   - Node.js gateway validates tokens
   - Token refresh mechanism

2. **Rate Limiting:**
   - Per-user rate limits
   - Per-IP rate limits
   - DDoS protection

3. **Network Security:**
   - TLS/SSL for all connections
   - VPC/private network for internal services
   - API gateway for public endpoints

4. **Data Privacy:**
   - Encrypt sensitive data
   - GDPR compliance
   - Audit logging

---

## Monitoring and Observability

1. **Metrics:**
   - Active WebSocket connections
   - Message throughput
   - Response times
   - Error rates

2. **Logging:**
   - Centralized logging (ELK/CloudWatch)
   - Structured logging
   - Request tracing

3. **Alerting:**
   - Connection threshold alerts
   - Error rate alerts
   - Service health alerts

---

## Conclusion

**Recommended Architecture: Option 3 (Node.js Gateway Layer)**

**Why:**
1. ✅ Best performance for 100K concurrent connections
2. ✅ Proper separation of concerns
3. ✅ Independent scaling of each layer
4. ✅ Maintainable and future-proof
5. ✅ Industry-standard approach

**Start Simple, Scale Gradually:**
- Begin with Laravel + Soketi (Node.js WebSocket server)
- Add dedicated Node.js gateway when needed
- Scale horizontally as users grow

**Key Success Factors:**
- Proper load testing at each phase
- Monitoring and alerting from day one
- Horizontal scaling capability
- Message queue for decoupling services

---

## Next Steps

1. **Proof of Concept:** Build simple Node.js gateway with 1K connections
2. **Load Testing:** Test with 10K, 50K, 100K connections
3. **Architecture Review:** Validate with team
4. **Implementation Plan:** Break down into sprints
5. **Infrastructure Setup:** Cloud provider, monitoring, etc.

---

*Last Updated: 2025-01-29*
*Author: AI Assistant*

