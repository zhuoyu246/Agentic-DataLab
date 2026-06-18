"""
Tests for configuration and security.
"""
import pytest
from core.config import Settings


@pytest.mark.unit
class TestConfig:
    """Test configuration class."""

    def test_jwt_secret_validation_dangerous_pattern(self):
        """Test that dangerous JWT secrets are rejected."""
        with pytest.raises(ValueError) as exc_info:
            Settings(jwt_secret_key="your-secret-key-change-this")
        assert "SECURITY ERROR" in str(exc_info.value)
        assert "your-secret-key" in str(exc_info.value).lower()

    def test_jwt_secret_validation_too_simple(self):
        """Test that simple JWT secrets are rejected."""
        with pytest.raises(ValueError) as exc_info:
            Settings(jwt_secret_key="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        assert "SECURITY ERROR" in str(exc_info.value)
        assert "too simple" in str(exc_info.value).lower()

    def test_jwt_secret_validation_success(self, mock_settings):
        """Test that valid JWT secret passes validation."""
        # Should not raise any exception
        assert mock_settings.jwt_secret_key is not None
        assert len(mock_settings.jwt_secret_key) >= 32

    def test_settings_defaults(self, mock_settings):
        """Test that settings have proper defaults."""
        assert mock_settings.app_env == "test"
        assert mock_settings.app_host == "127.0.0.1"
        assert mock_settings.app_port == 8000
        assert mock_settings.jwt_algorithm == "HS256"

    def test_settings_ensure_dirs_creates_directories(self, mock_settings, tmp_path):
        """Test that ensure_dirs creates required directories."""
        import os
        from pathlib import Path

        # Override data_root to use temp directory
        mock_settings.data_root = tmp_path / "storage"
        mock_settings.mlflow_artifact_root = str(tmp_path / "mlflow_artifacts")

        mock_settings.ensure_dirs()

        assert (tmp_path / "storage" / "hot").exists()
        assert (tmp_path / "storage" / "cold").exists()
        assert (tmp_path / "storage" / "projects").exists()
        assert (tmp_path / "mlflow_artifacts").exists()
