const Redis = require('ioredis');
const config = require('./config');
const logger = require('./logger');

class RedisClient {
  constructor() {
    this.publisher = null;
    this.subscriber = null;
    this.connected = false;
    this.subscribedChannels = new Set(); // Track subscribed channels
    this.channelCallbacks = new Map(); // Map channel to callbacks
    this.messageHandler = null; // Single message handler for all channels
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
      // Important: maxRetriesPerRequest must be null for pub/sub mode
      this.subscriber = new Redis({
        host: config.redis.host,
        port: config.redis.port,
        password: config.redis.password,
        db: config.redis.db,
        retryStrategy: config.redis.retryStrategy,
        maxRetriesPerRequest: null, // Must be null for pub/sub
        lazyConnect: config.redis.lazyConnect,
        enableOfflineQueue: false,
        showFriendlyErrorStack: true,
      });

      this.publisher.on('connect', () => {
        logger.info('Redis publisher connected');
      });

      this.subscriber.on('connect', () => {
        logger.info('Redis subscriber connected', {
          status: this.subscriber.status,
          mode: this.subscriber.mode,
        });
        this.connected = true;
        // Set up single message handler for all channels immediately
        // This must be done before any subscriptions
        this.setupMessageHandler();
      });

      // Also set up handler on 'ready' event (ioredis specific)
      this.subscriber.on('ready', () => {
        logger.info('Redis subscriber ready', {
          status: this.subscriber.status,
          mode: this.subscriber.mode,
        });
        // Ensure message handler is set up
        this.setupMessageHandler();
      });

      // Listen for subscription confirmation
      this.subscriber.on('psubscribe', (pattern, count) => {
        logger.debug('Redis pattern subscription confirmed', {
          pattern: pattern,
          count: count,
        });
      });

      this.subscriber.on('subscribe', (channel, count) => {
        logger.info('Redis subscription confirmed by server', {
          channel: channel,
          subscriberCount: count,
          totalSubscriptions: count,
          note: 'This confirms the subscription is active in Redis',
        });
        
        // Verify subscription count after confirmation
        if (this.publisher && this.publisher.status === 'ready') {
          this.publisher.pubsub('NUMSUB', channel).then((result) => {
            if (Array.isArray(result) && result.length >= 2) {
              const actualCount = parseInt(result[1], 10);
              logger.info('Verified subscription count after confirmation', {
                channel: channel,
                subscriberCount: actualCount,
              });
            }
          }).catch((err) => {
            // Ignore errors, subscription is still active
            logger.debug('Could not verify subscription count', {
              channel: channel,
              error: err.message,
            });
          });
        }
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
        
        // Set up message handler immediately after connection is established
        if (!this.messageHandler) {
          this.setupMessageHandler();
        }
        
        logger.info('Redis client initialized successfully', {
          publisherStatus: this.publisher.status,
          subscriberStatus: this.subscriber.status,
          subscriberMode: this.subscriber.mode,
          hasMessageHandler: !!this.messageHandler,
        });
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

  /**
   * Set up a single message handler for all channels
   */
  setupMessageHandler() {
    if (this.messageHandler) {
      logger.debug('Message handler already set up, skipping');
      return; // Already set up
    }

    if (!this.subscriber) {
      logger.error('Cannot set up message handler: subscriber not initialized');
      return;
    }

    this.messageHandler = (receivedChannel, message) => {
      try {
        // Log raw message received
        logger.info('📥 REDIS MESSAGE RECEIVED', {
          channel: receivedChannel,
          messageLength: message ? message.length : 0,
          messagePreview: message ? (message.length > 500 ? message.substring(0, 500) + '...' : message) : null,
          rawMessage: message, // Log full message
          subscribedChannels: Array.from(this.subscribedChannels),
          hasCallbacks: this.channelCallbacks.has(receivedChannel),
          callbackCount: this.channelCallbacks.get(receivedChannel)?.length || 0,
          timestamp: new Date().toISOString(),
        });

        // Get all callbacks for this channel
        const callbacks = this.channelCallbacks.get(receivedChannel);
        if (!callbacks || callbacks.length === 0) {
          logger.warn('Received message for channel with no callbacks', {
            channel: receivedChannel,
            message: message, // Log message even if no callbacks
            subscribedChannels: Array.from(this.subscribedChannels),
            allChannelsWithCallbacks: Array.from(this.channelCallbacks.keys()),
          });
          return;
        }

        // Parse message once
        let data;
        try {
          data = JSON.parse(message);
          logger.info('✅ REDIS MESSAGE PARSED', {
            channel: receivedChannel,
            messageType: data?.type || 'unknown',
            messageData: data, // Log full parsed message data
            callbackCount: callbacks.length,
            sessionId: data?.session_id || null,
            transactionId: data?.transaction_id || null,
            event: data?.event || null,
            chargerId: data?.data?.charger_id || data?.charger_id || null,
            userId: data?.user_id || data?.userId || null,
            timestamp: new Date().toISOString(),
          });
        } catch (error) {
          logger.error('❌ ERROR PARSING REDIS MESSAGE', {
            channel: receivedChannel,
            error: error.message,
            rawMessage: message, // Log full message even on parse error
            messagePreview: message ? message.substring(0, 500) : null,
            stack: error.stack,
          });
          return;
        }

        // Call all callbacks for this channel
        callbacks.forEach((callback, index) => {
          try {
            logger.info('📤 CALLING REDIS MESSAGE CALLBACK', {
              channel: receivedChannel,
              callbackIndex: index,
              totalCallbacks: callbacks.length,
              messageType: data?.type || 'unknown',
              messageData: data, // Log message data being passed to callback
            });
            callback(data);
            logger.debug('✅ Redis message callback executed successfully', {
              channel: receivedChannel,
              callbackIndex: index,
            });
          } catch (error) {
            logger.error('❌ ERROR IN REDIS MESSAGE CALLBACK', {
              channel: receivedChannel,
              callbackIndex: index,
              error: error.message,
              messageData: data, // Log message data that caused error
              stack: error.stack,
            });
          }
        });
      } catch (error) {
        logger.error('Error in Redis message handler', {
          channel: receivedChannel,
          error: error.message,
          stack: error.stack,
        });
      }
    };

    // Remove any existing listeners first to avoid duplicates
    this.subscriber.removeAllListeners('message');
    this.subscriber.removeAllListeners('pmessage');
    
    // Set up message handler with explicit binding
    const handler = (channel, message) => {
      logger.info('📨 REDIS MESSAGE EVENT FIRED (ioredis)', {
        channel: channel,
        messageLength: message ? message.length : 0,
        rawMessage: message, // Log full raw message
        handlerType: 'message',
        timestamp: new Date().toISOString(),
        subscriberStatus: this.subscriber.status,
        subscriberMode: this.subscriber.mode,
      });
      if (this.messageHandler) {
        this.messageHandler(channel, message);
      } else {
        logger.error('CRITICAL: messageHandler is null when message received!', {
          channel: channel,
          message: message, // Log message even if handler is null
        });
      }
    };
    
    // Attach the handler to the subscriber
    this.subscriber.on('message', handler);
    
    // Verify the listener is attached
    const listenerCount = this.subscriber.listenerCount('message');
    logger.info('Message event listener attached to subscriber', {
      listenerCount: listenerCount,
      subscriberStatus: this.subscriber.status,
      subscriberMode: this.subscriber.mode,
      hasMessageHandler: !!this.messageHandler,
    });
    
    if (listenerCount === 0) {
      logger.error('CRITICAL: No message listeners attached! Messages will not be received!');
    } else {
      logger.info('✅ Message handler successfully attached and ready to receive messages');
    }
    
    // Also listen for pmessage (pattern messages) just in case
    this.subscriber.on('pmessage', (pattern, channel, message) => {
      logger.info('📨 REDIS PATTERN MESSAGE RECEIVED', {
        pattern: pattern,
        channel: channel,
        messageLength: message ? message.length : 0,
        rawMessage: message, // Log full message
        timestamp: new Date().toISOString(),
      });
      // Call the regular message handler
      if (this.messageHandler) {
        this.messageHandler(channel, message);
      } else {
        logger.error('CRITICAL: messageHandler is null when pattern message received!', {
          pattern: pattern,
          channel: channel,
          message: message,
        });
      }
    });
    
    logger.info('Redis message handler set up successfully', {
      hasSubscriber: !!this.subscriber,
      subscriberStatus: this.subscriber.status,
      subscriberMode: this.subscriber.mode,
      listenerCount: listenerCount,
      subscribedChannels: Array.from(this.subscribedChannels),
    });
  }

  // Subscribe to a channel
  async subscribe(channel, callback) {
    if (!this.connected || !this.subscriber) {
      logger.warn('Redis not connected, skipping subscription', {
        channel: channel,
        connected: this.connected,
        hasSubscriber: !!this.subscriber,
      });
      return;
    }

    try {
      // Set up message handler if not already done
      if (!this.messageHandler) {
        logger.info('Setting up message handler during subscription', {
          channel: channel,
        });
        this.setupMessageHandler();
      }

      // Track callbacks for this channel
      if (!this.channelCallbacks.has(channel)) {
        this.channelCallbacks.set(channel, []);
      }
      this.channelCallbacks.get(channel).push(callback);

      logger.debug('Channel callback registered', {
        channel: channel,
        callbackCount: this.channelCallbacks.get(channel).length,
        hasMessageHandler: !!this.messageHandler,
      });

      // Subscribe to channel if not already subscribed
      if (!this.subscribedChannels.has(channel)) {
        // Ensure message handler is set up before subscribing
        if (!this.messageHandler) {
          logger.warn('Message handler not set up before subscription, setting up now', {
            channel: channel,
          });
          this.setupMessageHandler();
        }
        
        // Subscribe to the channel
        // Note: subscribe() returns the number of channels subscribed to
        logger.debug('Calling subscriber.subscribe()', {
          channel: channel,
          subscriberStatus: this.subscriber.status,
          subscriberMode: this.subscriber.mode,
          hasMessageHandler: !!this.messageHandler,
        });
        
        const result = await this.subscriber.subscribe(channel);
        this.subscribedChannels.add(channel);
        
        logger.debug('Subscribe command completed', {
          channel: channel,
          result: result,
          subscriberStatus: this.subscriber.status,
        });
        
        // Verify subscription using PUBSUB NUMSUB command on publisher connection
        // (subscriber connections can't execute regular commands)
        let subscriberCount = 0;
        try {
          if (this.publisher && this.publisher.status === 'ready') {
            const pubsubResult = await this.publisher.pubsub('NUMSUB', channel);
            // PUBSUB NUMSUB returns [channel, count]
            if (Array.isArray(pubsubResult) && pubsubResult.length >= 2) {
              subscriberCount = parseInt(pubsubResult[1], 10);
            }
          }
        } catch (err) {
          logger.debug('Could not verify subscription count (this is normal)', {
            channel: channel,
            error: err.message,
          });
        }

        logger.info('Subscribed to Redis channel', {
          channel: channel,
          totalSubscribedChannels: this.subscribedChannels.size,
          subscriptionResult: result,
          subscriberCount: subscriberCount,
          hasMessageHandler: !!this.messageHandler,
          subscriberStatus: this.subscriber.status,
          subscriberMode: this.subscriber.mode,
        });

        // Note: subscriberCount might be 0 immediately after subscription
        // The subscription is still active, Redis just needs a moment to register it
        if (subscriberCount === 0) {
          logger.debug('Subscriber count is 0 (may be timing issue, subscription is still active)', {
            channel: channel,
            subscriberStatus: this.subscriber.status,
            note: 'Subscription is active, count check may lag',
          });
        }
      } else {
        logger.debug('Channel already subscribed, adding callback', {
          channel: channel,
          callbackCount: this.channelCallbacks.get(channel).length,
        });
      }
    } catch (error) {
      logger.error('Failed to subscribe to Redis channel', {
        channel: channel,
        error: error.message,
        stack: error.stack,
      });
    }
  }

  // Unsubscribe from a channel
  async unsubscribe(channel) {
    if (!this.connected || !this.subscriber) {
      return;
    }

    try {
      // Remove callbacks for this channel
      this.channelCallbacks.delete(channel);

      // Only unsubscribe if no more callbacks exist
      if (this.subscribedChannels.has(channel) && this.channelCallbacks.get(channel)?.length === 0) {
        await this.subscriber.unsubscribe(channel);
        this.subscribedChannels.delete(channel);
        logger.info('Unsubscribed from Redis channel', {
          channel: channel,
          remainingSubscribedChannels: this.subscribedChannels.size,
        });
      } else {
        logger.debug('Channel still has callbacks, keeping subscription', {
          channel: channel,
          callbackCount: this.channelCallbacks.get(channel)?.length || 0,
        });
      }
    } catch (error) {
      logger.error('Failed to unsubscribe from Redis channel', {
        channel: channel,
        error: error.message,
        stack: error.stack,
      });
    }
  }

  // Publish to a channel
  async publish(channel, data) {
    if (!this.connected || !this.publisher) {
      logger.debug(`Redis not connected, skipping publish to ${channel}`);
      return Promise.reject(new Error('Redis not connected'));
    }
    try {
      const message = typeof data === 'string' ? data : JSON.stringify(data);
      const result = await this.publisher.publish(channel, message);
      logger.info(`Published to Redis channel`, {
        channel: channel,
        subscribers: result,
      });
      return result;
    } catch (error) {
      logger.error(`Failed to publish to Redis channel ${channel}:`, error.message);
      return Promise.reject(error);
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

  // Get subscription status
  getSubscriptionStatus() {
    return {
      connected: this.connected,
      subscribedChannels: Array.from(this.subscribedChannels),
      channelCount: this.subscribedChannels.size,
      channelsWithCallbacks: Object.fromEntries(
        Array.from(this.channelCallbacks.entries()).map(([channel, callbacks]) => [
          channel,
          callbacks.length
        ])
      ),
    };
  }
}

// Singleton instance
const redisClient = new RedisClient();

module.exports = redisClient;

