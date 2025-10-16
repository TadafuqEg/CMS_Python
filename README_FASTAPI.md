# FastAPI OCPP Central Management System

A comprehensive FastAPI-based OCPP 1.6/2.0.1 Central System with REST APIs, real-time monitoring, and Laravel CMS integration.

## 🚀 Features

### A. OCPP Layer
- **OCPP Protocol Support**: 1.6 JSON, optionally 2.0.1
- **WebSocket Server**: Central system endpoint (wss://cms.example.com/ocpp/CP_001)
- **Message Handling**: BootNotification, Heartbeat, StatusNotification, MeterValues, StartTransaction/StopTransaction, Authorize, DataTransfer
- **Message Queueing & Retry Mechanism**: Automatic retry for failed messages
- **Message Logging**: Store every message for audit & debugging
- **Error Handling**: Handle malformed messages, invalid IDs, etc.

### B. Device & Session Management
- **Charger Registration**: Automatic registration and grouping (by site, operator, etc.)
- **Real-time Status Tracking**: Available/Charging/Faulted/Offline status
- **Live Dashboard**: WebSocket-based real-time updates
- **Session Lifecycle Tracking**: Start time, stop time, kWh delivered, cost
- **Session History**: Exportable reports (CSV, PDF)
- **Firmware & Configuration Management**: OCPP remote commands
- **Remote Operations**: Start/Stop transaction, Unlock connector, Reset, Change availability

### C. User Management & Access Control
- **Roles & Permissions**: Admin, Operator, Maintenance, Viewer, Partner
- **Multi-Tenant Support**: Each client sees only their chargers
- **OAuth2 / JWT Authentication**: Secure API access
- **Audit Trail & Activity Logs**: Complete activity tracking
- **RBAC**: Role-Based Access Control

### D. Billing & Tariff Management
- **Tariff Configuration**: Flat rate, time-based, energy-based
- **Cost Calculation**: Per session with configurable tariffs
- **Session Tracking**: Energy delivered, duration, cost calculation

### E. Site & Organization Management
- **Hierarchical Data Model**: Organization → Site → Charger → Connector
- **Geo-location Support**: Ready for maps integration
- **Region-based Analytics**: Operator-based reporting

### F. Data Analytics & Reporting
- **Real-time Analytics**: Energy and usage analytics
- **Charger Reports**: Uptime & fault reports
- **Statistics**: Peak load and utilization statistics
- **Revenue Tracking**: Session count, energy delivered per day/week/month
- **Exportable Data**: CSV, JSON formats

### G. Integrations & APIs
- **REST API**: Complete REST API for mobile apps and 3rd-party integrations
- **WebSocket API**: Real-time updates
- **OpenAPI Documentation**: Swagger/OpenAPI 3.0 specification
- **Laravel CMS Integration**: Message queue integration
- **Vendor Extensions**: DataTransfer message support

### H. Security
- **HTTPS/WSS Enforcement**: SSL/TLS support
- **JWT Authentication**: Secure API access
- **Input Validation**: Comprehensive request validation
- **Role-based API Permissions**: Fine-grained access control

### I. Scalability & Infrastructure
- **FastAPI Framework**: High-performance async framework
- **Database Support**: SQLite (development), PostgreSQL (production)
- **Redis Integration**: Message queue and caching
- **Horizontal Scaling**: Ready for load balancing
- **Health Monitoring**: Comprehensive health checks

## 📋 API Endpoints

### System & Health APIs
- `GET /api/health` - System health check
- `GET /api/metrics` - Prometheus-compatible metrics
- `GET /api/status` - Detailed system status

### Charger Management APIs
- `GET /api/chargers` - List all chargers
- `GET /api/chargers/{charger_id}` - Get charger details
- `PUT /api/chargers/{charger_id}` - Update charger
- `DELETE /api/chargers/{charger_id}` - Disconnect charger
- `GET /api/chargers/{charger_id}/sessions` - Get charger sessions
- `GET /api/chargers/{charger_id}/statistics` - Get charger statistics

### OCPP Control APIs
- `POST /api/ocpp/remote/start` - Remote start transaction
- `POST /api/ocpp/remote/stop` - Remote stop transaction
- `POST /api/ocpp/unlock` - Unlock connector
- `POST /api/ocpp/reboot` - Reboot charger
- `POST /api/ocpp/configuration/get` - Get configuration
- `POST /api/ocpp/configuration/set` - Set configuration

### Logging & Diagnostics APIs
- `GET /api/logs` - Get system logs
- `GET /api/logs/summary` - Get logs summary
- `GET /api/logs/export` - Export logs
- `POST /api/diagnostics/upload` - Request diagnostics upload

### Internal APIs
- `POST /api/internal/event` - Receive events from Laravel CMS
- `POST /api/internal/broadcast` - Broadcast messages

### WebSocket Endpoints
- `/ocpp/{charger_id}` - OCPP charger connections
- `/master` - Master connections for broadcasting
- `/dashboard` - Real-time dashboard updates

## 🛠️ Installation

### Prerequisites
- Python 3.8+
- Redis (for message queue)
- SSL certificates (for production)

### Install Dependencies
```bash
pip install -r requirements_fastapi.txt
```

### Environment Configuration
Create a `.env` file:
```env
# Server Configuration
HOST=0.0.0.0
PORT=8000
DEBUG=true

# SSL Configuration (optional)
SSL_KEYFILE=key.pem
SSL_CERTFILE=cert.pem

# Database
DATABASE_URL=sqlite:///./ocpp_cms.db

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
SECRET_KEY=your-secret-key-change-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=30

# OCPP WebSocket
OCPP_WEBSOCKET_HOST=0.0.0.0
OCPP_WEBSOCKET_PORT=1025

# Laravel Integration
LARAVEL_API_URL=http://localhost:8080/api
LARAVEL_API_KEY=your-laravel-api-key
```

## 🚀 Running the Application

### Development Mode
```bash
python run_fastapi.py
```

### Production Mode
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### With SSL
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --ssl-keyfile key.pem --ssl-certfile cert.pem
```

## 📊 API Documentation

Once the server is running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## 🔧 Configuration

### Database Setup
The application uses SQLAlchemy with automatic table creation. For production, use PostgreSQL:

```env
DATABASE_URL=postgresql://user:password@localhost/ocpp_cms
```

### Redis Setup
Redis is used for message queue and caching:

```bash
# Install Redis
sudo apt-get install redis-server

# Start Redis
redis-server
```

### SSL Certificates
For production, generate SSL certificates:

```bash
# Generate self-signed certificate (development)
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
```

## 🔐 Authentication

### JWT Token Generation
```python
from app.core.security import create_access_token

# Create token
token = create_access_token(data={"sub": "user@example.com", "roles": ["admin"]})
```

### API Usage
```bash
# Include token in requests
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" http://localhost:8000/api/chargers
```

## 📡 WebSocket Connections

### Charger Connection
```javascript
const ws = new WebSocket('wss://localhost:1025/ocpp/CP_001', ['ocpp1.6']);
```

### Dashboard Connection
```javascript
const ws = new WebSocket('wss://localhost:8000/dashboard', {
  headers: {
    'Authorization': 'Bearer YOUR_JWT_TOKEN'
  }
});
```

## 🔄 Laravel CMS Integration

### Message Queue Events
The system sends events to Laravel CMS via Redis:

```python
# Boot notification
await mq_bridge.send_boot_notification(charger_id, charger_data)

# Transaction events
await mq_bridge.send_transaction_start(charger_id, session_data)
await mq_bridge.send_transaction_stop(charger_id, session_data)

# Status updates
await mq_bridge.send_status_notification(charger_id, status_data)
```

### HTTP Integration
Laravel can send commands via HTTP:

```bash
curl -X POST http://localhost:8000/api/internal/event \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "RemoteStartTransaction",
    "charger_id": "CP_001",
    "payload": {"id_tag": "USER1234"}
  }'
```

## 📈 Monitoring

### Health Checks
```bash
# System health
curl http://localhost:8000/api/health

# Metrics
curl http://localhost:8000/api/metrics
```

### Logging
Logs are stored in the database and can be exported:

```bash
# Export logs
curl "http://localhost:8000/api/logs/export?format=csv&limit=1000"
```

## 🧪 Testing

### Run Tests
```bash
pytest tests/
```

### Test OCPP Connection
Use the provided test scripts:
```bash
python test_universal_websocket.py
python test_master_broadcast.py
```

## 🚀 Deployment

### Docker Deployment
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements_fastapi.txt .
RUN pip install -r requirements_fastapi.txt

COPY . .
EXPOSE 8000 1025

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Production Considerations
- Use PostgreSQL for production database
- Configure Redis clustering for high availability
- Set up SSL certificates
- Configure proper logging
- Set up monitoring and alerting
- Use a reverse proxy (nginx)
- Configure firewall rules

## 📝 License

MIT License - see LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📞 Support

For support and questions:
- Email: support@ocpp-cms.com
- Documentation: http://localhost:8000/docs
- Issues: GitHub Issues
