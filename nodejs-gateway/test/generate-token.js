/**
 * Generate a test JWT token for WebSocket gateway authentication
 * 
 * Usage:
 *   node test/generate-token.js
 * 
 * Or with custom user ID:
 *   node test/generate-token.js 123
 */

const jwt = require('jsonwebtoken');
const config = require('../src/config');

// Get user ID from command line argument or use default
const userId = process.argv[2] || 123;
const email = process.argv[3] || 'test@example.com';

// Generate token payload
const payload = {
  id: userId,
  user_id: parseInt(userId),
  email: email,
  name: 'Test User',
  iss: config.jwt.issuer || 'laravel-backend', // Issuer
  iat: Math.floor(Date.now() / 1000), // Issued at
  exp: Math.floor(Date.now() / 1000) + (24 * 60 * 60) // Expires in 24 hours
};

try {
  // Generate token
  const token = jwt.sign(
    payload,
    config.jwt.secret,
    { algorithm: config.jwt.algorithm || 'HS256' }
  );

  console.log('\n✅ Token generated successfully!\n');
  console.log('Token:');
  console.log(token);
  console.log('\n' + '='.repeat(80));
  console.log('\nPayload:');
  console.log(JSON.stringify(payload, null, 2));
  console.log('\n' + '='.repeat(80));
  console.log('\nWebSocket URL:');
  console.log(`ws://localhost:8080?token=${token}`);
  console.log('\n' + '='.repeat(80));
  console.log('\n⚠️  Important:');
  console.log(`   - JWT_SECRET: ${config.jwt.secret}`);
  console.log(`   - Algorithm: ${config.jwt.algorithm}`);
  console.log(`   - Issuer: ${config.jwt.issuer}`);
  console.log('\n   Make sure these match your Laravel configuration!');
  console.log('\n');

} catch (error) {
  console.error('❌ Error generating token:', error.message);
  console.error('\nMake sure:');
  console.error('  1. JWT_SECRET is set in .env file');
  console.error('  2. jsonwebtoken package is installed (npm install)');
  console.error('  3. The secret matches your Laravel JWT_SECRET');
  process.exit(1);
}

