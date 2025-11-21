const WebSocket = require('ws');
const config = require('./config');
const logger = require('./logger');
const redisClient = require('./redis-client');
const authService = require('./auth');

class ConnectionManager {
  constructor() {
    this.connections = new Map(); // Map<userId, Set<WebSocket>>
    this.userConnections = new Map(); // Map<WebSocket, userId>
    this.guestConnections = new Set(); // Set<WebSocket> for guest connections
    this.publicChannelSubscribed = false; // Track if public channel is subscribed
    this.connectionStats = {
      total: 0,
      active: 0,
      byUser: new Map(),
      guests: 0,
    };
  }

  /**
   * Handle new WebSocket connection
   * Supports both authenticated users and guest connections (for public channels only)
   */
  async handleConnection(ws, req) {
    try {
      // Extract and validate token
      const token = authService.extractToken(req);
      
      // If no token, allow as guest connection (public channels only)
      if (!token) {
        logger.info('Guest connection (no token) - will only receive public channel updates');
        this.addGuestConnection(ws);
        
        // Subscribe to public channels
        if (redisClient.isConnected()) {
          await this.subscribeToPublicChannels();
        }
        
        // Set up message handlers (limited for guests)
        this.setupGuestMessageHandlers(ws);
        
        // Send welcome message
        this.sendMessage(ws, {
          type: 'connected',
          timestamp: new Date().toISOString(),
          isGuest: true,
          message: 'Connected as guest. You will receive public charger status updates.',
        });
        
        logger.info(`Guest connected. Total connections: ${this.connectionStats.active} (${this.connectionStats.guests} guests)`);
        return;
      }

      // Validate token for authenticated users
      const user = await authService.validateToken(token);
      if (!user) {
        logger.warn('Connection rejected: Invalid token');
        ws.close(1008, 'Invalid authentication token');
        return;
      }

      const userId = user.id || user.user_id;
      if (!userId) {
        logger.warn('Connection rejected: Invalid user data');
        ws.close(1008, 'Invalid user data');
        return;
      }

      // Store connection
      this.addConnection(userId, ws);

      // Subscribe to user-specific Redis channels (if Redis is available)
      if (redisClient.isConnected()) {
        await this.subscribeToUserChannels(userId);
        // Also subscribe to public channels for authenticated users
        await this.subscribeToPublicChannels();
      } else {
        logger.debug(`Redis not available, skipping channel subscription for user ${userId}`);
      }

      // Set up message handlers
      this.setupMessageHandlers(ws, userId, token);

      // Send welcome message
      this.sendMessage(ws, {
        type: 'connected',
        timestamp: new Date().toISOString(),
        userId: userId,
        isGuest: false,
      });

      logger.info(`User ${userId} connected. Total connections: ${this.connectionStats.active}`);
    } catch (error) {
      logger.error('Error handling connection:', error);
      ws.close(1011, 'Server error');
    }
  }

  /**
   * Add connection for a user
   */
  addConnection(userId, ws) {
    if (!this.connections.has(userId)) {
      this.connections.set(userId, new Set());
    }
    this.connections.get(userId).add(ws);

    this.userConnections.set(ws, userId);
    this.connectionStats.total++;
    this.connectionStats.active++;
    this.connectionStats.byUser.set(userId, (this.connectionStats.byUser.get(userId) || 0) + 1);

    // Store connection in Redis (for cluster mode)
    if (redisClient.isConnected()) {
      redisClient.set(`ws:${userId}:${config.server.instanceId}`, '1', 3600).catch(err => {
        logger.debug('Error storing connection in Redis:', err.message);
      });
    }
  }

  /**
   * Add guest connection
   */
  addGuestConnection(ws) {
    this.guestConnections.add(ws);
    this.connectionStats.active++;
    this.connectionStats.guests++;
  }

  /**
   * Remove connection
   */
  removeConnection(ws) {
    // Check if it's a guest connection
    if (this.guestConnections.has(ws)) {
      this.guestConnections.delete(ws);
      this.connectionStats.active--;
      this.connectionStats.guests--;
      logger.info(`Guest disconnected. Active connections: ${this.connectionStats.active} (${this.connectionStats.guests} guests)`);
      return;
    }

    const userId = this.userConnections.get(ws);
    if (!userId) {
      return;
    }

    const userConnections = this.connections.get(userId);
    if (userConnections) {
      userConnections.delete(ws);
      if (userConnections.size === 0) {
        this.connections.delete(userId);
        // Unsubscribe from Redis channels
        this.unsubscribeFromUserChannels(userId);
      }
    }

    this.userConnections.delete(ws);
    this.connectionStats.active--;
    const count = (this.connectionStats.byUser.get(userId) || 1) - 1;
    if (count > 0) {
      this.connectionStats.byUser.set(userId, count);
    } else {
      this.connectionStats.byUser.delete(userId);
    }

    // Remove from Redis
    if (redisClient.isConnected()) {
      redisClient.del(`ws:${userId}:${config.server.instanceId}`).catch(err => {
        logger.debug('Error removing connection from Redis:', err.message);
      });
    }

    logger.info(`User ${userId} disconnected. Active connections: ${this.connectionStats.active}`);
  }

  /**
   * Subscribe to public Redis channels (charger status updates)
   * This is called once and shared by all connections
   */
  async subscribeToPublicChannels() {
    if (!redisClient.isConnected()) {
      return;
    }

    // Only subscribe once to the public channel
    if (this.publicChannelSubscribed) {
      return;
    }

    const publicChannel = 'charger:updates';

    await redisClient.subscribe(publicChannel, (data) => {
      logger.info('🔔 Received public charger update from Redis', {
        channel: publicChannel,
        messageType: data?.type || 'unknown',
        chargerId: data?.charger_id || null,
        stationId: data?.station_id || null,
        status: data?.status || null,
      });
      
      // Broadcast to all connections (both authenticated and guest)
      this.broadcastToAll(data);
    });

    this.publicChannelSubscribed = true;
    logger.info('Subscribed to public channels', {
      channel: publicChannel,
      redisConnected: redisClient.isConnected(),
    });
  }

  /**
   * Subscribe to user-specific Redis channels
   */
  async subscribeToUserChannels(userId) {
    if (!redisClient.isConnected()) {
      return;
    }

    const channels = [
      `user:${userId}:notifications`,
      `user:${userId}:session_updates`,
      // Note: charger_updates removed from user channels - now using public channel
    ];

    for (const channel of channels) {
      await redisClient.subscribe(channel, (data) => {
        logger.info('🔔 CALLBACK TRIGGERED - Received Redis message in connection manager', {
          channel: channel,
          userId: userId,
          messageType: data?.type || 'unknown',
          sessionId: data?.session_id || null,
          transactionId: data?.transaction_id || null,
          event: data?.event || null,
          chargerId: data?.data?.charger_id || null,
          hasData: !!data,
        });
        this.broadcastToUser(userId, data);
      });
    }

    logger.info('Subscribed to user channels', {
      userId: userId,
      channels: channels,
      redisConnected: redisClient.isConnected(),
    });
  }

  /**
   * Unsubscribe from user-specific Redis channels
   */
  async unsubscribeFromUserChannels(userId) {
    if (!redisClient.isConnected()) {
      return;
    }

    const channels = [
      `user:${userId}:notifications`,
      `user:${userId}:session_updates`,
      // Note: charger_updates removed - using public channel now
    ];

    for (const channel of channels) {
      await redisClient.unsubscribe(channel);
    }
  }

  /**
   * Set up message handlers for guest connections (limited functionality)
   */
  setupGuestMessageHandlers(ws) {
    // Handle incoming messages (guests can only receive, not send)
    ws.on('message', async (data) => {
      try {
        const message = JSON.parse(data.toString());
        logger.debug('Guest attempted to send message (not allowed)', { message });
        this.sendError(ws, 'Guest connections are read-only. Please authenticate to send messages.');
      } catch (error) {
        logger.error('Error handling guest message:', error);
        this.sendError(ws, 'Invalid message format');
      }
    });

    // Handle connection close
    ws.on('close', () => {
      this.removeConnection(ws);
    });

    // Handle errors
    ws.on('error', (error) => {
      logger.error('Guest WebSocket error:', error);
      this.removeConnection(ws);
    });

    // Handle pong (response to ping) - CRITICAL: Without this, guest connections will be terminated
    ws.on('pong', () => {
      ws.isAlive = true;
      logger.debug('Guest connection pong received, connection is alive');
    });

    // Set up heartbeat
    ws.isAlive = true;
    const heartbeatInterval = setInterval(() => {
      if (ws.isAlive === false) {
        logger.warn('Guest connection did not respond to ping, terminating', {
          readyState: ws.readyState,
        });
        clearInterval(heartbeatInterval);
        ws.terminate();
        return;
      }
      ws.isAlive = false;
      ws.ping();
      logger.debug('Sent ping to guest connection');
    }, config.server.heartbeatInterval);

    ws.on('close', () => {
      clearInterval(heartbeatInterval);
    });
  }

  /**
   * Set up message handlers for WebSocket
   */
  setupMessageHandlers(ws, userId, token) {
    // Handle incoming messages
    ws.on('message', async (data) => {
      try {
        const message = JSON.parse(data.toString());
        await this.handleMessage(ws, userId, token, message);
      } catch (error) {
        logger.error('Error handling message:', error);
        this.sendError(ws, 'Invalid message format');
      }
    });

    // Handle connection close
    ws.on('close', () => {
      this.removeConnection(ws);
    });

    // Handle errors
    ws.on('error', (error) => {
      logger.error(`WebSocket error for user ${userId}:`, error);
      this.removeConnection(ws);
    });

    // Handle pong (response to ping)
    ws.on('pong', () => {
      ws.isAlive = true;
    });

    // Set up heartbeat
    ws.isAlive = true;
    const heartbeatInterval = setInterval(() => {
      if (ws.isAlive === false) {
        clearInterval(heartbeatInterval);
        ws.terminate();
        return;
      }
      ws.isAlive = false;
      ws.ping();
    }, config.server.heartbeatInterval);

    ws.on('close', () => {
      clearInterval(heartbeatInterval);
    });
  }

  /**
   * Handle incoming message from client
   */
  async handleMessage(ws, userId, token, message) {
    const { action, data } = message;

    logger.debug(`Received message from user ${userId}: ${action}`);

    // Forward message to Laravel backend
    const response = await this.forwardToLaravel(userId, token, action, data);

    // Send response back to client
    if (response) {
      this.sendMessage(ws, {
        type: 'response',
        action: action,
        data: response,
        timestamp: new Date().toISOString(),
      });
    }
  }

  /**
   * Forward message to Laravel backend
   */
  async forwardToLaravel(userId, token, action, data) {
    const axios = require('axios');
    const config = require('./config');

    try {
      const response = await axios.post(
        `${config.laravel.apiUrl}/api/websocket/message`,
        {
          action,
          data,
          userId,
        },
        {
          timeout: config.laravel.timeout,
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }
      );

      return response.data;
    } catch (error) {
      logger.error('Error forwarding message to Laravel:', error.message);
      return {
        error: 'Failed to process request',
        message: error.message,
      };
    }
  }

  /**
   * Broadcast message to all connections (both authenticated and guest)
   * Used for public channels like charger status updates
   */
  broadcastToAll(data) {
    const message = typeof data === 'string' ? data : JSON.stringify(data);
    let sentCount = 0;
    let failedCount = 0;
    const messageType = typeof data === 'object' ? data?.type : 'unknown';

    // Broadcast to all authenticated users
    this.connections.forEach((userConnections, userId) => {
      userConnections.forEach((ws) => {
        if (ws.readyState === WebSocket.OPEN) {
          try {
            ws.send(message);
            sentCount++;
          } catch (error) {
            failedCount++;
            logger.error('Error broadcasting to authenticated user', {
              userId,
              error: error.message,
            });
            this.removeConnection(ws);
          }
        }
      });
    });

    // Broadcast to all guest connections
    this.guestConnections.forEach((ws) => {
      if (ws.readyState === WebSocket.OPEN) {
        try {
          ws.send(message);
          sentCount++;
        } catch (error) {
          failedCount++;
          logger.error('Error broadcasting to guest connection', {
            error: error.message,
          });
          this.removeConnection(ws);
        }
      } else {
        this.removeConnection(ws);
      }
    });

    if (sentCount > 0) {
      logger.info('Broadcasted public message to all connections', {
        messageType,
        sentCount,
        failedCount,
        totalConnections: this.connectionStats.active,
        authenticatedUsers: this.connections.size,
        guests: this.guestConnections.size,
      });
    }
  }

  /**
   * Broadcast message to all connections of a user
   */
  broadcastToUser(userId, data) {
    const userConnections = this.connections.get(userId);
    if (!userConnections) {
      logger.warn('No active connections found for user', {
        userId: userId,
        messageType: data?.type || 'unknown',
      });
      return;
    }

    const message = typeof data === 'string' ? data : JSON.stringify(data);
    let sentCount = 0;
    let failedCount = 0;
    const messageType = typeof data === 'object' ? data?.type : 'unknown';

    userConnections.forEach((ws, index) => {
      const readyStateNames = {
        0: 'CONNECTING',
        1: 'OPEN',
        2: 'CLOSING',
        3: 'CLOSED'
      };
      
      logger.info('🔍 Checking WebSocket connection before send', {
        userId: userId,
        connectionIndex: index,
        readyState: ws.readyState,
        readyStateName: readyStateNames[ws.readyState] || 'UNKNOWN',
        isOpen: ws.readyState === WebSocket.OPEN,
        messageType: messageType,
        messageLength: message.length,
        messagePreview: typeof message === 'string' ? message.substring(0, 100) : JSON.stringify(message).substring(0, 100),
      });

      if (ws.readyState === WebSocket.OPEN) {
        try {
          logger.info('📤 Attempting to send message to WebSocket', {
            userId: userId,
            connectionIndex: index,
            messageType: messageType,
            messageLength: message.length,
            messageContent: typeof message === 'string' ? message : JSON.stringify(message),
          });
          
          ws.send(message);
          sentCount++;
          
          logger.info('✅ Successfully called ws.send() - message should be sent', {
            userId: userId,
            connectionIndex: index,
            messageType: messageType,
            sessionId: data?.session_id || null,
            transactionId: data?.transaction_id || null,
            event: data?.event || null,
            messageLength: message.length,
          });
        } catch (error) {
          failedCount++;
          logger.error('❌ Error sending message to WebSocket connection', {
            userId: userId,
            connectionIndex: index,
            messageType: messageType,
            error: error.message,
            stack: error.stack,
          });
          this.removeConnection(ws);
        }
      } else {
        logger.warn('⚠️ WebSocket connection not open, skipping send', {
          userId: userId,
          connectionIndex: index,
          readyState: ws.readyState,
          readyStateName: readyStateNames[ws.readyState] || 'UNKNOWN',
        });
        this.removeConnection(ws);
      }
    });

    if (sentCount > 0) {
      logger.info('Broadcasted message to WebSocket connections', {
        userId: userId,
        messageType: messageType,
        sentCount: sentCount,
        failedCount: failedCount,
        totalConnections: userConnections.size,
        sessionId: data?.session_id || null,
        transactionId: data?.transaction_id || null,
        event: data?.event || null,
      });
    } else if (failedCount > 0) {
      logger.warn('Failed to send message to any WebSocket connections', {
        userId: userId,
        messageType: messageType,
        failedCount: failedCount,
        totalConnections: userConnections.size,
      });
    }
  }

  /**
   * Send message to specific WebSocket
   */
  sendMessage(ws, data) {
    if (ws.readyState === WebSocket.OPEN) {
      try {
        const message = JSON.stringify(data);
        ws.send(message);
        const userId = this.userConnections.get(ws);
        logger.debug('Sent message to WebSocket', {
          userId: userId || 'unknown',
          messageType: data?.type || 'unknown',
          readyState: ws.readyState,
        });
      } catch (error) {
        const userId = this.userConnections.get(ws);
        logger.error('Error sending message to WebSocket', {
          userId: userId || 'unknown',
          messageType: data?.type || 'unknown',
          error: error.message,
          stack: error.stack,
        });
      }
    } else {
      const userId = this.userConnections.get(ws);
      logger.warn('Cannot send message: WebSocket not open', {
        userId: userId || 'unknown',
        messageType: data?.type || 'unknown',
        readyState: ws.readyState,
      });
    }
  }

  /**
   * Send error message
   */
  sendError(ws, message) {
    this.sendMessage(ws, {
      type: 'error',
      message: message,
      timestamp: new Date().toISOString(),
    });
  }

  /**
   * Get connection statistics
   */
  getStats() {
    return {
      total: this.connectionStats.total,
      active: this.connectionStats.active,
      uniqueUsers: this.connections.size,
      guests: this.connectionStats.guests,
      byUser: Object.fromEntries(this.connectionStats.byUser),
      instanceId: config.server.instanceId,
    };
  }

  /**
   * Get connections for a specific user
   */
  getUserConnections(userId) {
    return this.connections.get(userId) || new Set();
  }
}

// Singleton instance
const connectionManager = new ConnectionManager();

module.exports = connectionManager;

