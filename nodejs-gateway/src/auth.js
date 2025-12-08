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
    const tokenPreview = token ? `${token.substring(0, 20)}...` : 'null';
    logger.info('Token validation request (local)', {
      tokenPreview: tokenPreview,
      tokenLength: token ? token.length : 0,
      hasCache: this.tokenCache.has(token),
      timestamp: new Date().toISOString(),
    });

    try {
      // Check cache first
      if (this.tokenCache.has(token)) {
        const cached = this.tokenCache.get(token);
        if (Date.now() < cached.expiresAt) {
          logger.info('Token validation response (local - cached)', {
            tokenPreview: tokenPreview,
            valid: true,
            source: 'cache',
            userId: cached.payload?.id || cached.payload?.user_id || null,
            timestamp: new Date().toISOString(),
          });
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

      logger.info('Token validation response (local - verified)', {
        tokenPreview: tokenPreview,
        valid: true,
        source: 'jwt_verification',
        userId: decoded?.id || decoded?.user_id || null,
        email: decoded?.email || null,
        timestamp: new Date().toISOString(),
      });

      return decoded;
    } catch (error) {
      logger.info('Token validation response (local - failed)', {
        tokenPreview: tokenPreview,
        valid: false,
        source: 'jwt_verification',
        error: error.message,
        errorType: error.name,
        timestamp: new Date().toISOString(),
      });
      return null;
    }
  }

  /**
   * Validate token with Laravel backend
   */
  async validateTokenWithLaravel(token) {
    const tokenPreview = token ? `${token.substring(0, 20)}...` : 'null';
    const requestStartTime = Date.now();
    
    logger.info('Token validation request (Laravel)', {
      tokenPreview: tokenPreview,
      tokenLength: token ? token.length : 0,
      apiUrl: `${config.laravel.apiUrl}/api/auth/validate-token`,
      timeout: config.laravel.timeout,
      timestamp: new Date().toISOString(),
    });

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

      const responseTime = Date.now() - requestStartTime;

      if (response.data && response.data.valid) {
        logger.info('Token validation response (Laravel - success)', {
          tokenPreview: tokenPreview,
          valid: true,
          source: 'laravel_api',
          userId: response.data.user?.id || response.data.user?.user_id || null,
          email: response.data.user?.email || null,
          responseTime: `${responseTime}ms`,
          statusCode: response.status,
          timestamp: new Date().toISOString(),
        });
        return response.data.user;
      }

      logger.info('Token validation response (Laravel - invalid)', {
        tokenPreview: tokenPreview,
        valid: false,
        source: 'laravel_api',
        responseTime: `${responseTime}ms`,
        statusCode: response.status,
        responseData: response.data,
        timestamp: new Date().toISOString(),
      });

      return null;
    } catch (error) {
      const responseTime = Date.now() - requestStartTime;
      
      logger.info('Token validation response (Laravel - error)', {
        tokenPreview: tokenPreview,
        valid: false,
        source: 'laravel_api',
        error: error.message,
        errorType: error.code || error.name,
        responseTime: `${responseTime}ms`,
        statusCode: error.response?.status || null,
        timestamp: new Date().toISOString(),
      });
      
      return null;
    }
  }

  /**
   * Validate token (try local first, then Laravel)
   */
  async validateToken(token) {
    const tokenPreview = token ? `${token.substring(0, 20)}...` : 'null';
    const validationStartTime = Date.now();
    
    logger.info('Token validation request (main)', {
      tokenPreview: tokenPreview,
      tokenLength: token ? token.length : 0,
      timestamp: new Date().toISOString(),
    });

    if (!token) {
      logger.info('Token validation response (main - no token)', {
        tokenPreview: tokenPreview,
        valid: false,
        reason: 'no_token_provided',
        timestamp: new Date().toISOString(),
      });
      return null;
    }

    // Try local validation first (faster)
    const localResult = await this.validateTokenLocal(token);
    if (localResult) {
      const totalTime = Date.now() - validationStartTime;
      logger.info('Token validation response (main - success via local)', {
        tokenPreview: tokenPreview,
        valid: true,
        validationMethod: 'local',
        userId: localResult?.id || localResult?.user_id || null,
        totalTime: `${totalTime}ms`,
        timestamp: new Date().toISOString(),
      });
      return localResult;
    }

    // Fallback to Laravel validation
    const laravelResult = await this.validateTokenWithLaravel(token);
    if (laravelResult) {
      const totalTime = Date.now() - validationStartTime;
      logger.info('Token validation response (main - success via Laravel)', {
        tokenPreview: tokenPreview,
        valid: true,
        validationMethod: 'laravel',
        userId: laravelResult?.id || laravelResult?.user_id || null,
        totalTime: `${totalTime}ms`,
        timestamp: new Date().toISOString(),
      });
      return laravelResult;
    }

    const totalTime = Date.now() - validationStartTime;
    logger.info('Token validation response (main - failed)', {
      tokenPreview: tokenPreview,
      valid: false,
      validationMethod: 'both_failed',
      totalTime: `${totalTime}ms`,
      timestamp: new Date().toISOString(),
    });

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

