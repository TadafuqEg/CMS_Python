const jwt = require('jsonwebtoken');
const axios = require('axios');
const config = require('./config');
const logger = require('./logger');

class AuthService {
  constructor() {
    this.tokenCache = new Map(); // Cache validated tokens
    this.cacheTTL = 5 * 60 * 1000; // 5 minutes
  }

  /**
   * Extract token from WebSocket connection
   */
  extractToken(req) {
    // Try to get token from query parameter
    const url = new URL(req.url, `http://${req.headers.host}`);
    const token = url.searchParams.get('token');
    
    if (token) {
      return token;
    }

    // Try to get from Authorization header (if upgraded from HTTP)
    const authHeader = req.headers.authorization;
    if (authHeader && authHeader.startsWith('Bearer ')) {
      return authHeader.substring(7);
    }

    return null;
  }

  /**
   * Validate JWT token locally
   */
  async validateTokenLocal(token) {
    try {
      // Check cache first
      if (this.tokenCache.has(token)) {
        const cached = this.tokenCache.get(token);
        if (Date.now() < cached.expiresAt) {
          return cached.payload;
        }
        this.tokenCache.delete(token);
      }

      // Verify JWT
      const decoded = jwt.verify(token, config.jwt.secret, {
        algorithms: [config.jwt.algorithm],
        issuer: config.jwt.issuer,
      });

      // Cache the token
      this.tokenCache.set(token, {
        payload: decoded,
        expiresAt: Date.now() + this.cacheTTL,
      });

      return decoded;
    } catch (error) {
      logger.debug('Token validation failed:', error.message);
      return null;
    }
  }

  /**
   * Validate token with Laravel backend
   */
  async validateTokenWithLaravel(token) {
    try {
      const response = await axios.post(
        `${config.laravel.apiUrl}/api/auth/validate-token`,
        { token },
        {
          timeout: config.laravel.timeout,
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (response.data && response.data.valid) {
        return response.data.user;
      }

      return null;
    } catch (error) {
      logger.error('Error validating token with Laravel:', error.message);
      return null;
    }
  }

  /**
   * Validate token (try local first, then Laravel)
   */
  async validateToken(token) {
    if (!token) {
      return null;
    }

    // Try local validation first (faster)
    const localResult = await this.validateTokenLocal(token);
    if (localResult) {
      return localResult;
    }

    // Fallback to Laravel validation
    const laravelResult = await this.validateTokenWithLaravel(token);
    if (laravelResult) {
      return laravelResult;
    }

    return null;
  }

  /**
   * Clear token from cache
   */
  clearTokenCache(token) {
    this.tokenCache.delete(token);
  }

  /**
   * Clear expired tokens from cache
   */
  clearExpiredTokens() {
    const now = Date.now();
    for (const [token, data] of this.tokenCache.entries()) {
      if (now >= data.expiresAt) {
        this.tokenCache.delete(token);
      }
    }
  }
}

// Singleton instance
const authService = new AuthService();

// Clean up expired tokens every minute
setInterval(() => {
  authService.clearExpiredTokens();
}, 60 * 1000);

module.exports = authService;

