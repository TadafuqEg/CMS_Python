/**
 * Simple token generator that doesn't require config
 * 
 * Usage:
 *   node test/generate-token-simple.js YOUR_SECRET_KEY
 */

const jwt = require('jsonwebtoken');

// Get secret from command line or use default (for testing only)
const secret = process.argv[2] || process.env.JWT_SECRET || 'your-secret-key-change-this';
const userId = process.argv[3] || 123;
const email = process.argv[4] || 'test@example.com';

if (!process.argv[2] && !process.env.JWT_SECRET) {
  console.warn('⚠️  Warning: Using default secret. Set JWT_SECRET in .env or pass as argument.');
  console.warn('   Usage: node test/generate-token-simple.js YOUR_SECRET_KEY [user_id] [email]\n');
}

// Generate token payload
const payload = {
  id: parseInt(userId),
  user_id: parseInt(userId),
  email: email,
  name: 'Test User',
  iss: 'laravel-backend', // Issuer
  iat: Math.floor(Date.now() / 1000), // Issued at
  exp: Math.floor(Date.now() / 1000) + (24 * 60 * 60) // Expires in 24 hours
};

try {
  // Generate token
  const token = jwt.sign(
    payload,
    secret,
    { algorithm: 'HS256' }
  );

  console.log('\n✅ Token generated!\n');
  console.log('Token:');
  console.log(token);
  console.log('\n' + '─'.repeat(80));
  console.log('\nWebSocket Connection URL:');
  console.log(`ws://localhost:8080?token=${token}`);
  console.log('\n' + '─'.repeat(80));
  console.log('\nToken Details:');
  console.log(`  User ID: ${userId}`);
  console.log(`  Email: ${email}`);
  console.log(`  Secret: ${secret.substring(0, 20)}...`);
  console.log(`  Expires: ${new Date(payload.exp * 1000).toLocaleString()}`);
  console.log('\n');

  // Also output as JSON for easy copying
  console.log('JSON Format:');
  console.log(JSON.stringify({ token, ...payload }, null, 2));
  console.log('\n');

} catch (error) {
  console.error('❌ Error generating token:', error.message);
  console.error('\nMake sure jsonwebtoken is installed: npm install jsonwebtoken');
  process.exit(1);
}


