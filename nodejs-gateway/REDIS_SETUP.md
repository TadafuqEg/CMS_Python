# Redis Setup Guide

## Quick Start Options

### Option 1: Disable Redis (Development/Testing)

If you don't need Redis for development/testing, you can disable it:

**Update `.env`:**
```env
REDIS_ENABLED=false
```

The gateway will start without Redis. Note: Real-time notifications via pub/sub will not be available.

### Option 2: Install Redis Locally

#### Windows

1. **Download Redis for Windows:**
   - Download from: https://github.com/microsoftarchive/redis/releases
   - Or use WSL (Windows Subsystem for Linux)

2. **Using WSL (Recommended):**
   ```bash
   # In WSL terminal
   sudo apt update
   sudo apt install redis-server
   sudo service redis-server start
   ```

3. **Using Docker (Easiest):**
   ```bash
   docker run -d -p 6379:6379 --name redis redis:latest
   ```

#### macOS

```bash
brew install redis
brew services start redis
```

#### Linux

```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### Option 3: Use Redis Cloud (Free Tier Available)

1. Sign up at: https://redis.com/try-free/
2. Create a free database
3. Get connection details
4. Update `.env`:
   ```env
   REDIS_HOST=your-redis-host.redis.cloud
   REDIS_PORT=12345
   REDIS_PASSWORD=your-password
   ```

## Verify Redis is Running

```bash
# Test connection
redis-cli ping
# Should return: PONG

# Or check if port is open
# Windows
netstat -an | findstr 6379

# Linux/Mac
netstat -an | grep 6379
```

## Configuration

Update `nodejs-gateway/.env`:

```env
# Enable/disable Redis
REDIS_ENABLED=true

# Redis connection
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
```

## Troubleshooting

### Connection Refused Error

**Error:** `ECONNREFUSED`

**Solutions:**
1. Check if Redis is running:
   ```bash
   redis-cli ping
   ```

2. Check Redis is listening on correct port:
   ```bash
   # Default port is 6379
   netstat -an | grep 6379
   ```

3. Check firewall settings

4. If Redis is on a different machine, verify host and port

5. Temporarily disable Redis for testing:
   ```env
   REDIS_ENABLED=false
   ```

### Connection Timeout

**Error:** `Connection timeout`

**Solutions:**
1. Check network connectivity
2. Verify Redis host and port
3. Check firewall rules
4. Increase connection timeout in config

## Production Setup

For production, use:
- Redis Cluster (for high availability)
- Redis Sentinel (for automatic failover)
- Redis Cloud or AWS ElastiCache (managed service)

## What Works Without Redis

The gateway will work without Redis, but these features will be limited:
- ✅ WebSocket connections (works)
- ✅ Message forwarding to Laravel (works)
- ✅ Authentication (works)
- ❌ Real-time notifications via pub/sub (requires Redis)
- ❌ Multi-instance coordination (requires Redis)

For development/testing, you can use the gateway without Redis. For production with real-time notifications, Redis is required.

