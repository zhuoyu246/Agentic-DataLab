"""
Tests for health check endpoints.
"""
import pytest


@pytest.mark.api
class TestHealthEndpoints:
    """Test health check API endpoints."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert data["service"] == "Agentic DataLab API"
        assert "status" in data
        assert data["status"] == "running"

    def test_api_root_endpoint(self, client):
        """Test API root endpoint."""
        response = client.get("/api/v1")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "routes" in data
