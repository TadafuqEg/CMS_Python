const cluster = require('cluster');
const os = require('os');
const config = require('./config');
const logger = require('./logger');

if (config.cluster.enabled && cluster.isPrimary) {
  // Master process - spawn workers
  const numWorkers = config.cluster.workers || os.cpus().length;
  
  logger.info(`Starting cluster mode with ${numWorkers} workers`);
  logger.info(`Master process PID: ${process.pid}`);

  // Spawn workers
  for (let i = 0; i < numWorkers; i++) {
    const worker = cluster.fork();
    logger.info(`Worker ${worker.process.pid} started`);
  }

  // Handle worker exit
  cluster.on('exit', (worker, code, signal) => {
    logger.warn(`Worker ${worker.process.pid} died (${signal || code}). Restarting...`);
    const newWorker = cluster.fork();
    logger.info(`New worker ${newWorker.process.pid} started`);
  });

  // Handle worker online
  cluster.on('online', (worker) => {
    logger.info(`Worker ${worker.process.pid} is online`);
  });

  // Handle messages from workers
  cluster.on('message', (worker, message) => {
    if (message.type === 'stats') {
      logger.info(`Worker ${worker.process.pid} stats:`, message.data);
    }
  });

} else {
  // Worker process - start the server
  const WebSocketGateway = require('./server');
  const gateway = new WebSocketGateway();
  gateway.start().catch((error) => {
    logger.error('Worker failed to start:', error);
    process.exit(1);
  });
}

