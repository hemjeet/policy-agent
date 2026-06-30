import logging
import time
import functools
from sqlalchemy.exc import OperationalError, TimeoutError as SATimeoutError

logger = logging.getLogger(__name__)

RETRYABLE_EXCEPTIONS = (
    OperationalError,
    SATimeoutError,
    ConnectionError,
    TimeoutError,
)



def retry_on_db_error(max_attempts = 3, base_delay = 0.5):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except RETRYABLE_EXCEPTIONS as e:
                    if attempt == max_attempts:
                        raise
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "DB error in %s: %s. Retrying in %.1fs...",
                        func.__name__, e, delay,
                    )
                    time.sleep(delay)
        return wrapper
    return decorator