require('dotenv').config();

module.exports = {
  server: {
    port: parseInt(process.env.PORT || 8080, 10),
    host: process.env.HOST || '0.0.0.0',
    instanceId: process.env.INSTANCE_ID || `gateway-${process.pid}`,
    maxConnections: parseInt(process.env.MAX_CONNECTIONS_PER_INSTANCE || 10000, 10),
    heartbeatInterval: parseInt(process.env.HEARTBEAT_INTERVAL || 30000, 10),
    connectionTimeout: parseInt(process.env.CONNECTION_TIMEOUT || 60000, 10),
  },
  
  laravel: {
    apiUrl: process.env.LARAVEL_API_URL || 'http://localhost:8000',
    timeout: parseInt(process.env.LARAVEL_API_TIMEOUT || 5000, 10),
  },
  
  jwt: {
    secret: process.env.JWT_SECRET || 'your-secret-key',
    algorithm: process.env.JWT_ALGORITHM || 'HS256',
    issuer: process.env.JWT_ISSUER || 'laravel-backend',
  },
  
  redis: {
    enabled: process.env.REDIS_ENABLED !== 'false', // Default to true, set to 'false' to disable
    host: process.env.REDIS_HOST || 'localhost',
    port: parseInt(process.env.REDIS_PORT || 6379, 10),
    password: process.env.REDIS_PASSWORD || undefined,
    db: parseInt(process.env.REDIS_DB || 0, 10),
    retryStrategy: (times) => {
      const delay = Math.min(times * 50, 2000);
      return delay;
    },
    maxRetriesPerRequest: null, // Set to null for pub/sub operations
    lazyConnect: true, // Don't connect immediately
  },
  
  cluster: {
    enabled: process.env.CLUSTER_MODE === 'true',
    workers: parseInt(process.env.CLUSTER_WORKERS || 4, 10),
  },
  
  logging: {
    level: process.env.LOG_LEVEL || 'info',
    file: process.env.LOG_FILE || 'logs/gateway.log',
  },
};

