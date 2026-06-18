"""
Rate limiting middleware for Agentic-DataLab.

Uses slowapi for request rate limiting based on IP address.
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


# Create limiter instance
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


def register_rate_limiter(app):
    """
    Register rate limiter with the FastAPI app.

    Args:
        app: FastAPI application instance
    """
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Predefined rate limit decorators for common use cases
def rate_limit_login():
    """Rate limit for login endpoint: 5 requests per minute."""
    return limiter.limit("5/minute")


def rate_limit_register():
    """Rate limit for registration endpoint: 3 requests per hour."""
    return limiter.limit("3/hour")


def rate_limit_chat():
    """Rate limit for chat/agent endpoints: 20 requests per minute."""
    return limiter.limit("20/minute")


def rate_limit_upload():
    """Rate limit for upload endpoints: 10 requests per minute."""
    return limiter.limit("10/minute")
