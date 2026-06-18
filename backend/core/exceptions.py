"""
Custom exception classes for Agentic-DataLab.

Provides a hierarchy of exceptions for better error handling and reporting.
"""
from typing import Any, Optional


class DataLabException(Exception):
    """Base exception for all Agentic-DataLab errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(DataLabException):
    """Raised when input validation fails."""
    pass


class AuthenticationError(DataLabException):
    """Raised when authentication fails."""
    pass


class AuthorizationError(DataLabException):
    """Raised when user lacks required permissions."""
    pass


class ResourceNotFoundError(DataLabException):
    """Raised when a requested resource does not exist."""
    pass


class ResourceConflictError(DataLabException):
    """Raised when a resource conflict occurs (e.g., duplicate)."""
    pass


class AgentExecutionError(DataLabException):
    """Raised when an agent fails to execute properly."""
    pass


class DatabaseError(DataLabException):
    """Raised when a database operation fails."""
    pass


class ExternalServiceError(DataLabException):
    """Raised when an external service (LLM, Redis, etc.) fails."""
    pass


class RateLimitExceededError(DataLabException):
    """Raised when rate limit is exceeded."""
    pass


class ConfigurationError(DataLabException):
    """Raised when configuration is invalid or missing."""
    pass
