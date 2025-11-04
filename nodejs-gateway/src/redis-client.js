const Redis = require('ioredis');
const config = require('./config');
const logger = require('./logger');

class RedisClient {
  constructor() {
    this.publisher = null;
    this.subscriber = null;
    this.connected = false;
  }

  async connect() {
    // Check if Redis is enabled
    if (!config.redis.enabled) {
      logger.warn('Redis is disabled. Running in standalone mode (no pub/sub).');
      this.connected = false;
      return;
    }

    try {
      // Publisher connection for sending messages
      this.publisher = new Redis({
        host: config.redis.host,
        port: config.redis.port,
        password: config.redis.password,
        db: config.redis.db,
        retryStrategy: config.redis.retryStrategy,
        maxRetriesPerRequest: config.redis.maxRetriesPerRequest,
        lazyConnect: config.redis.lazyConnect,
        enableOfflineQueue: false, // Don't queue commands when disconnected
      });

      // Subscriber connection for receiving messages
      this.subscriber = new Redis({
        host: config.redis.host,
        port: config.redis.port,
        password: config.redis.password,
        db: config.redis.db,
        retryStrategy: config.redis.retryStrategy,
        maxRetriesPerRequest: config.redis.maxRetriesPerRequest,
        lazyConnect: config.redis.lazyConnect,
        enableOfflineQueue: false,
      });

      this.publisher.on('connect', () => {
        logger.info('Redis publisher connected');
      });

      this.subscriber.on('connect', () => {
        logger.info('Redis subscriber connected');
        this.connected = true;
      });

      this.publisher.on('error', (err) => {
        // Only log error if we're not already disconnected
        if (this.connected) {
          logger.warn('Redis publisher error:', err.message);
        }
        this.connected = false;
      });

      this.subscriber.on('error', (err) => {
        // Only log error if we're not already disconnected
        if (this.connected) {
          logger.warn('Redis subscriber error:', err.message);
        }
        this.connected = false;
      });

      // Try to connect with timeout
      const connectPromise = Promise.all([
        this.publisher.connect().catch(err => {
          logger.warn('Failed to connect Redis publisher:', err.message);
          throw err;
        }),
        this.subscriber.connect().catch(err => {
          logger.warn('Failed to connect Redis subscriber:', err.message);
          throw err;
        })
      ]);

      // Set timeout for connection attempt
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => reject(new Error('Redis connection timeout')), 5000);
      });

      try {
        await Promise.race([connectPromise, timeoutPromise]);
        
        // Test connection
        await this.publisher.ping();
        await this.subscriber.ping();
        
        logger.info('Redis client initialized successfully');
        this.connected = true;
      } catch (error) {
        // Connection failed, but don't throw - allow server to start without Redis
        logger.warn(`Redis connection failed: ${error.message}. Running in standalone mode.`);
        logger.warn('Real-time notifications via Redis pub/sub will not be available.');
        this.connected = false;
        
        // Clean up failed connections
        if (this.publisher) {
          try {
            await this.publisher.quit();
          } catch (e) {
            // Ignore cleanup errors
          }
        }
        if (this.subscriber) {
          try {
            await this.subscriber.quit();
          } catch (e) {
            // Ignore cleanup errors
          }
        }
        this.publisher = null;
        this.subscriber = null;
      }
    } catch (error) {
      logger.warn(`Redis initialization error: ${error.message}. Running in standalone mode.`);
      this.connected = false;
    }
  }

  async disconnect() {
    if (this.publisher) {
      await this.publisher.quit();
    }
    if (this.subscriber) {
      await this.subscriber.quit();
    }
    this.connected = false;
    logger.info('Redis client disconnected');
  }

  // Subscribe to a channel
  async subscribe(channel, callback) {
    if (!this.connected || !this.subscriber) {
      logger.debug(`Redis not connected, skipping subscription to ${channel}`);
      return;
    }
    try {
      await this.subscriber.subscribe(channel);
      this.subscriber.on('message', (receivedChannel, message) => {
        if (receivedChannel === channel) {
          try {
            const data = JSON.parse(message);
            callback(data);
          } catch (error) {
            logger.error('Error parsing Redis message:', error);
          }
        }
      });
      logger.debug(`Subscribed to Redis channel: ${channel}`);
    } catch (error) {
      logger.warn(`Failed to subscribe to Redis channel ${channel}:`, error.message);
    }
  }

  // Unsubscribe from a channel
  async unsubscribe(channel) {
    if (!this.connected) {
      return;
    }
    await this.subscriber.unsubscribe(channel);
    logger.debug(`Unsubscribed from Redis channel: ${channel}`);
  }

  // Publish to a channel
  async publish(channel, data) {
    if (!this.connected || !this.publisher) {
      logger.debug(`Redis not connected, skipping publish to ${channel}`);
      return;
    }
    try {
      const message = typeof data === 'string' ? data : JSON.stringify(data);
      await this.publisher.publish(channel, message);
      logger.debug(`Published to Redis channel: ${channel}`);
    } catch (error) {
      logger.warn(`Failed to publish to Redis channel ${channel}:`, error.message);
    }
  }

  // Set key-value pair
  async set(key, value, ttl = null) {
    if (!this.connected || !this.publisher) {
      logger.debug(`Redis not connected, skipping set for key ${key}`);
      return null;
    }
    try {
      if (ttl) {
        return await this.publisher.setex(key, ttl, value);
      }
      return await this.publisher.set(key, value);
    } catch (error) {
      logger.warn(`Failed to set Redis key ${key}:`, error.message);
      return null;
    }
  }

  // Get value by key
  async get(key) {
    if (!this.connected || !this.publisher) {
      logger.debug(`Redis not connected, skipping get for key ${key}`);
      return null;
    }
    try {
      return await this.publisher.get(key);
    } catch (error) {
      logger.warn(`Failed to get Redis key ${key}:`, error.message);
      return null;
    }
  }

  // Delete key
  async del(key) {
    if (!this.connected) {
      return;
    }
    return await this.publisher.del(key);
  }

  // Check if connected
  isConnected() {
    return this.connected;
  }
}

// Singleton instance
const redisClient = new RedisClient();

module.exports = redisClient;

