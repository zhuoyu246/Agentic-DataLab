"""
Timeout and retry utilities for Agentic-DataLab agents.

Provides decorators for handling timeouts and automatic retries with exponential backoff.
"""
import asyncio
import functools
import time
from typing import Any, Callable, TypeVar

from core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


def timeout(seconds: float):
    """
    Timeout decorator for async functions.

    Args:
        seconds: Timeout in seconds

    Raises:
        asyncio.TimeoutError: If function execution exceeds timeout

    Example:
        @timeout(30.0)
        async def my_function():
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                logger.error(
                    "function_timeout",
                    function=func.__name__,
                    timeout_seconds=seconds,
                )
                raise asyncio.TimeoutError(
                    f"Function {func.__name__} timed out after {seconds} seconds"
                )
        return wrapper
    return decorator


def retry(
    max_attempts: int = 3,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """
    Retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        backoff_factor: Exponential backoff factor (delay = backoff_factor ** attempt)
        exceptions: Tuple of exceptions to catch and retry

    Example:
        @retry(max_attempts=3, backoff_factor=2.0)
        async def my_function():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        logger.error(
                            "function_retry_exhausted",
                            function=func.__name__,
                            attempts=attempt,
                            error=str(e),
                        )
                        raise

                    delay = backoff_factor ** (attempt - 1)
                    logger.warning(
                        "function_retry_attempt",
                        function=func.__name__,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay_seconds=delay,
                        error=str(e),
                    )

                    await asyncio.sleep(delay)

            # Should never reach here, but for type safety
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def timeout_and_retry(
    timeout_seconds: float = 120.0,
    max_attempts: int = 3,
    backoff_factor: float = 2.0,
):
    """
    Combined timeout and retry decorator.

    Args:
        timeout_seconds: Timeout in seconds per attempt
        max_attempts: Maximum number of retry attempts
        backoff_factor: Exponential backoff factor

    Example:
        @timeout_and_retry(timeout_seconds=60.0, max_attempts=3)
        async def my_agent_function():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @retry(max_attempts=max_attempts, backoff_factor=backoff_factor, exceptions=(asyncio.TimeoutError, Exception))
        @timeout(timeout_seconds)
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await func(*args, **kwargs)
        return wrapper
    return decorator
