"""
Database utility functions with retry logic for handling SQLite locking issues
"""
import asyncio
import logging
from typing import Any, Callable, Optional
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class DatabaseRetryError(Exception):
    """Custom exception for database retry failures"""
    pass

async def db_operation_with_retry(
    operation: Callable[[Session], Any],
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    operation_name: str = "database operation"
) -> Any:
    """
    Execute a database operation with retry logic for handling SQLite locking issues
    
    Args:
        operation: Function that takes a Session and performs database operations
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        operation_name: Name of the operation for logging purposes
    
    Returns:
        Result of the database operation
        
    Raises:
        DatabaseRetryError: If all retry attempts fail
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            # Create a new session for each attempt
            from app.models.database import SessionLocal
            db = SessionLocal()
            
            try:
                result = operation(db)
                db.commit()
                logger.debug(f"{operation_name} succeeded on attempt {attempt + 1}")
                return result
            except Exception as e:
                db.rollback()
                raise e
            finally:
                db.close()
                
        except OperationalError as e:
            last_exception = e
            if "database is locked" in str(e).lower():
                if attempt < max_retries:
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(f"{operation_name} failed due to database lock (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.2f}s: {e}")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"{operation_name} failed after {max_retries + 1} attempts due to database lock: {e}")
                    break
            else:
                # Non-locking error, don't retry
                logger.error(f"{operation_name} failed with non-retryable error: {e}")
                raise DatabaseRetryError(f"{operation_name} failed: {e}")
                
        except Exception as e:
            # Non-database error, don't retry
            logger.error(f"{operation_name} failed with non-database error: {e}")
            raise DatabaseRetryError(f"{operation_name} failed: {e}")
    
    # All retries exhausted
    raise DatabaseRetryError(f"{operation_name} failed after {max_retries + 1} attempts due to database lock: {last_exception}")

def sync_db_operation_with_retry(
    operation: Callable[[Session], Any],
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    operation_name: str = "database operation"
) -> Any:
    """
    Synchronous version of db_operation_with_retry for non-async contexts
    
    Args:
        operation: Function that takes a Session and performs database operations
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        operation_name: Name of the operation for logging purposes
    
    Returns:
        Result of the database operation
        
    Raises:
        DatabaseRetryError: If all retry attempts fail
    """
    import time
    
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            # Create a new session for each attempt
            from app.models.database import SessionLocal
            db = SessionLocal()
            
            try:
                result = operation(db)
                db.commit()
                logger.debug(f"{operation_name} succeeded on attempt {attempt + 1}")
                return result
            except Exception as e:
                db.rollback()
                raise e
            finally:
                db.close()
                
        except OperationalError as e:
            last_exception = e
            if "database is locked" in str(e).lower():
                if attempt < max_retries:
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(f"{operation_name} failed due to database lock (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.2f}s: {e}")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"{operation_name} failed after {max_retries + 1} attempts due to database lock: {e}")
                    break
            else:
                # Non-locking error, don't retry
                logger.error(f"{operation_name} failed with non-retryable error: {e}")
                raise DatabaseRetryError(f"{operation_name} failed: {e}")
                
        except Exception as e:
            # Non-database error, don't retry
            logger.error(f"{operation_name} failed with non-database error: {e}")
            raise DatabaseRetryError(f"{operation_name} failed: {e}")
    
    # All retries exhausted
    raise DatabaseRetryError(f"{operation_name} failed after {max_retries + 1} attempts due to database lock: {last_exception}")
