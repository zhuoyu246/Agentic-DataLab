import pytest
from core.exceptions import (
    ValidationError,
    AuthenticationError,
    ResourceNotFoundError,
    AgentExecutionError,
)


def test_validation_error():
    error = ValidationError("Invalid input", details={"field": "email"})
    assert error.message == "Invalid input"
    assert error.details == {"field": "email"}


def test_authentication_error():
    error = AuthenticationError("Invalid credentials")
    assert error.message == "Invalid credentials"


def test_resource_not_found():
    error = ResourceNotFoundError("User not found", details={"user_id": 123})
    assert "User not found" in error.message
    assert error.details["user_id"] == 123


def test_agent_execution_error():
    error = AgentExecutionError("Agent failed", details={"agent": "sql"})
    assert error.message == "Agent failed"
    assert error.details["agent"] == "sql"
