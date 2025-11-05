/**
 * Complete Test Script for Start/Stop Charging Flow
 * 
 * This script tests the complete flow:
 * 1. Connect to WebSocket gateway
 * 2. Send start_charging command
 * 3. Wait for response
 * 4. Send stop_charging command
 * 5. Wait for response
 * 
 * Usage:
 *   node test/charging-flow-test.js YOUR_TOKEN
 * 
 * Or with charger ID:
 *   node test/charging-flow-test.js YOUR_TOKEN CP001
 */

const WebSocket = require('ws');

// Get token and charger ID from command line
const token = process.argv[2];
const chargerId = process.argv[3] || 'CP001';
const wsUrl = process.argv[4] || 'ws://localhost:8080';

if (!token) {
  console.error('❌ Error: Token is required');
  console.error('\nUsage:');
  console.error('  node test/charging-flow-test.js YOUR_TOKEN [CHARGER_ID] [WS_URL]');
  console.error('\nExample:');
  console.error(`  node test/charging-flow-test.js ${token || 'YOUR_TOKEN'} CP001 ws://localhost:8080`);
  process.exit(1);
}

console.log('🚀 Starting Charging Flow Test\n');
console.log('═'.repeat(80));
console.log(`WebSocket URL: ${wsUrl}`);
console.log(`Charger ID: ${chargerId}`);
console.log(`Token: ${token.substring(0, 50)}...`);
console.log('═'.repeat(80));
console.log('\n');

let ws = null;
let testStep = 0;
let startTime = Date.now();

// Test steps
const steps = [
  { name: 'Connect', action: 'connect' },
  { name: 'Start Charging', action: 'start_charging' },
  { name: 'Wait (5 seconds)', action: 'wait' },
  { name: 'Stop Charging', action: 'stop_charging' },
  { name: 'Disconnect', action: 'disconnect' },
];

function log(message, type = 'info') {
  const timestamp = new Date().toLocaleTimeString();
  const icon = {
    info: 'ℹ️',
    success: '✅',
    error: '❌',
    warning: '⚠️',
    send: '📤',
    receive: '📥',
  }[type] || 'ℹ️';
  console.log(`[${timestamp}] ${icon} ${message}`);
}

function connect() {
  return new Promise((resolve, reject) => {
    log(`Connecting to ${wsUrl}...`, 'info');
    
    const urlWithToken = `${wsUrl}?token=${encodeURIComponent(token)}`;
    ws = new WebSocket(urlWithToken);
    
    ws.on('open', () => {
      log('Connected successfully!', 'success');
      resolve();
    });
    
    ws.on('message', (data) => {
      try {
        const message = JSON.parse(data.toString());
        log(`Received: ${JSON.stringify(message, null, 2)}`, 'receive');
        handleMessage(message);
      } catch (e) {
        log(`Received (raw): ${data.toString()}`, 'receive');
      }
    });
    
    ws.on('error', (error) => {
      log(`Connection error: ${error.message}`, 'error');
      reject(error);
    });
    
    ws.on('close', (code, reason) => {
      log(`Connection closed (code: ${code}, reason: ${reason || 'No reason'})`, 'warning');
    });
    
    // Timeout after 10 seconds
    setTimeout(() => {
      if (ws.readyState !== WebSocket.OPEN) {
        reject(new Error('Connection timeout'));
      }
    }, 10000);
  });
}

function sendMessage(action, data) {
  return new Promise((resolve) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      log('Not connected, cannot send message', 'error');
      resolve();
      return;
    }
    
    const message = {
      action: action,
      data: data
    };
    
    log(`Sending: ${JSON.stringify(message, null, 2)}`, 'send');
    ws.send(JSON.stringify(message));
    
    // Wait a bit for response
    setTimeout(resolve, 2000);
  });
}

function handleMessage(message) {
  if (message.type === 'connected') {
    log('Connection confirmed by server', 'success');
  } else if (message.type === 'response') {
    if (message.data && message.data.success) {
      log(`Action '${message.action}' succeeded`, 'success');
      if (message.data.session_id) {
        log(`Session ID: ${message.data.session_id}`, 'info');
      }
      if (message.data.transaction_id) {
        log(`Transaction ID: ${message.data.transaction_id}`, 'info');
      }
    } else {
      log(`Action '${message.action}' failed: ${message.data?.error || 'Unknown error'}`, 'error');
    }
  } else if (message.type === 'error') {
    log(`Error: ${message.message}`, 'error');
  }
}

async function runTest() {
  try {
    // Step 1: Connect
    log(`\n[Step ${testStep + 1}/${steps.length}] ${steps[testStep].name}`, 'info');
    await connect();
    await sleep(1000);
    
    // Step 2: Start Charging
    testStep++;
    log(`\n[Step ${testStep + 1}/${steps.length}] ${steps[testStep].name}`, 'info');
    await sendMessage('start_charging', {
      charger_id: chargerId,
      connector_id: 1
    });
    await sleep(1000);
    
    // Step 3: Wait
    testStep++;
    log(`\n[Step ${testStep + 1}/${steps.length}] ${steps[testStep].name}`, 'info');
    log('Waiting 5 seconds before stopping...', 'info');
    await sleep(5000);
    
    // Step 4: Stop Charging
    testStep++;
    log(`\n[Step ${testStep + 1}/${steps.length}] ${steps[testStep].name}`, 'info');
    await sendMessage('stop_charging', {
      charger_id: chargerId
    });
    await sleep(2000);
    
    // Step 5: Disconnect
    testStep++;
    log(`\n[Step ${testStep + 1}/${steps.length}] ${steps[testStep].name}`, 'info');
    if (ws) {
      ws.close();
      log('Disconnected', 'success');
    }
    
    const duration = ((Date.now() - startTime) / 1000).toFixed(2);
    log(`\n✅ Test completed in ${duration} seconds`, 'success');
    log('\n' + '═'.repeat(80), 'info');
    
  } catch (error) {
    log(`\n❌ Test failed: ${error.message}`, 'error');
    if (ws) {
      ws.close();
    }
    process.exit(1);
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Run the test
runTest();



