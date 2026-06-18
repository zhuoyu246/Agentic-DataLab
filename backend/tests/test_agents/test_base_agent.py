"""
Tests for base agent functionality.
"""
import pytest
from agents.base import BaseAgent, AgentContext, AgentResult


@pytest.mark.agent
@pytest.mark.unit
class TestBaseAgent:
    """Test base agent class."""

    def test_agent_has_name(self):
        """Test that BaseAgent has required attributes."""
        assert hasattr(BaseAgent, 'name')
        assert hasattr(BaseAgent, 'description')

    def test_agent_run_method_exists(self):
        """Test that BaseAgent has run method."""
        assert hasattr(BaseAgent, 'run')
        assert callable(getattr(BaseAgent, 'run'))

    @pytest.mark.asyncio
    async def test_agent_result_structure(self):
        """Test AgentResult structure."""
        result = AgentResult(
            message="Test message",
            degraded=False
        )
        assert result.message == "Test message"
        assert result.degraded is False
