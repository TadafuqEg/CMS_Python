const WebSocket = require('ws');
const http = require('http');
const express = require('express');
const config = require('./config');
const logger = require('./logger');
const redisClient = require('./redis-client');
const connectionManager = require('./connection-manager');

class WebSocketGateway {
  constructor() {
    this.server = null;
    this.wss = null;
    this.httpApp = express();
  }

  /**
   * Initialize the gateway server
   */
  async initialize() {
    try {
      // Connect to Redis (non-blocking - will continue even if Redis fails)
      try {
        await redisClient.connect();
      } catch (error) {
        logger.warn('Redis connection failed, continuing without Redis:', error.message);
        logger.warn('Gateway will work in standalone mode. Real-time notifications via pub/sub will not be available.');
      }

      // Set up HTTP server for health checks
      this.setupHttpServer();

      // Set up WebSocket server
      this.setupWebSocketServer();

      logger.info(`WebSocket Gateway initialized on port ${config.server.port}`);
      logger.info(`Instance ID: ${config.server.instanceId}`);
      logger.info(`Max connections: ${config.server.maxConnections}`);
      logger.info(`Redis status: ${redisClient.isConnected() ? 'connected' : 'disconnected (standalone mode)'}`);
    } catch (error) {
      logger.error('Failed to initialize gateway:', error);
      throw error;
    }
  }

  /**
   * Set up HTTP server for health checks and stats
   */
  setupHttpServer() {
    this.httpApp.use(express.json());

    // Health check endpoint
    this.httpApp.get('/health', (req, res) => {
      res.json({
        status: 'ok',
        instance: config.server.instanceId,
        uptime: process.uptime(),
        connections: connectionManager.getStats(),
        redis: redisClient.isConnected() ? 'connected' : 'disconnected',
      });
    });

    // Statistics endpoint
    this.httpApp.get('/stats', (req, res) => {
      res.json({
        instance: config.server.instanceId,
        stats: connectionManager.getStats(),
        memory: process.memoryUsage(),
        uptime: process.uptime(),
      });
    });

    // Graceful shutdown endpoint
    this.httpApp.post('/shutdown', (req, res) => {
      res.json({ message: 'Shutting down...' });
      setTimeout(() => {
        this.shutdown();
      }, 1000);
    });
  }

  /**
   * Set up WebSocket server
   */
  setupWebSocketServer() {
    // Create HTTP server
    this.server = http.createServer(this.httpApp);

    // Create WebSocket server
    this.wss = new WebSocket.Server({
      server: this.server,
      perMessageDeflate: false, // Disable compression for better performance
      maxPayload: 1024 * 1024, // 1MB max message size
      clientTracking: true,
    });

    // Handle new WebSocket connections
    this.wss.on('connection', async (ws, req) => {
      // Check connection limit
      const stats = connectionManager.getStats();
      if (stats.active >= config.server.maxConnections) {
        logger.warn(`Connection limit reached: ${stats.active}/${config.server.maxConnections}`);
        ws.close(1008, 'Server at capacity');
        return;
      }

      // Handle the connection
      await connectionManager.handleConnection(ws, req);
    });

    // Handle server errors
    this.wss.on('error', (error) => {
      logger.error('WebSocket server error:', error);
    });

    // Log connection statistics periodically
    setInterval(() => {
      const stats = connectionManager.getStats();
      logger.info(`Connections: ${stats.active} active, ${stats.uniqueUsers} unique users`);
    }, 60000); // Every minute
  }

  /**
   * Start the server
   */
  async start() {
    try {
      await this.initialize();

      this.server.listen(config.server.port, config.server.host, () => {
        logger.info(`WebSocket Gateway started on ${config.server.host}:${config.server.port}`);
        logger.info(`Environment: ${process.env.NODE_ENV || 'development'}`);
      });

      // Handle graceful shutdown
      process.on('SIGTERM', () => this.shutdown());
      process.on('SIGINT', () => this.shutdown());

      // Handle uncaught errors
      process.on('uncaughtException', (error) => {
        logger.error('Uncaught exception:', error);
        this.shutdown();
      });

      process.on('unhandledRejection', (reason, promise) => {
        logger.error('Unhandled rejection:', reason);
      });
    } catch (error) {
      logger.error('Failed to start server:', error);
      process.exit(1);
    }
  }

  /**
   * Graceful shutdown
   */
  async shutdown() {
    logger.info('Shutting down WebSocket Gateway...');

    // Stop accepting new connections
    if (this.wss) {
      this.wss.close(() => {
        logger.info('WebSocket server closed');
      });
    }

    // Close all connections
    const stats = connectionManager.getStats();
    logger.info(`Closing ${stats.active} active connections...`);

    // Close HTTP server
    if (this.server) {
      this.server.close(() => {
        logger.info('HTTP server closed');
      });
    }

    // Disconnect Redis
    await redisClient.disconnect();

    logger.info('Gateway shutdown complete');
    process.exit(0);
  }
}

// Start the server if this file is run directly
if (require.main === module) {
  const gateway = new WebSocketGateway();
  gateway.start().catch((error) => {
    logger.error('Failed to start gateway:', error);
    process.exit(1);
  });
}

module.exports = WebSocketGateway;

