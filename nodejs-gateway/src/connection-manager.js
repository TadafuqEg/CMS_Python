const WebSocket = require('ws');
const config = require('./config');
const logger = require('./logger');
const redisClient = require('./redis-client');
const authService = require('./auth');

class ConnectionManager {
  constructor() {
    this.connections = new Map(); // Map<userId, Set<WebSocket>>
    this.userConnections = new Map(); // Map<WebSocket, userId>
    this.connectionStats = {
      total: 0,
      active: 0,
      byUser: new Map(),
    };
  }

  /**
   * Handle new WebSocket connection
   */
  async handleConnection(ws, req) {
    try {
      // Extract and validate token
      const token = authService.extractToken(req);
      if (!token) {
        logger.warn('Connection rejected: No token provided');
        ws.close(1008, 'Authentication required');
        return;
      }

      // Validate token
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
   * Remove connection
   */
  removeConnection(ws) {
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
   * Subscribe to user-specific Redis channels
   */
  async subscribeToUserChannels(userId) {
    if (!redisClient.isConnected()) {
      return;
    }

    const channels = [
      `user:${userId}:notifications`,
      `user:${userId}:session_updates`,
      `user:${userId}:charger_updates`,
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
      `user:${userId}:charger_updates`,
    ];

    for (const channel of channels) {
      await redisClient.unsubscribe(channel);
    }
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

