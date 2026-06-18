"""
Pytest configuration and fixtures for Agentic-DataLab tests.
"""
import os
import secrets
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment variables before importing the app
TEST_JWT_SECRET = secrets.token_urlsafe(32)
os.environ["JWT_SECRET_KEY"] = TEST_JWT_SECRET
os.environ["APP_ENV"] = "test"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # Use test DB 15
os.environ["POSTGRES_DSN"] = "sqlite:///:memory:"  # In-memory SQLite for tests

from main import create_app
from core.database import get_db
from models.user import Base


# Test database engine (in-memory SQLite)
TEST_SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="session")
def engine():
    """Create test database engine."""
    engine = create_engine(
        TEST_SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(engine):
    """Create a new database session for each test."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with dependency override."""
    app = create_app()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client, test_user):
    """Generate authentication headers for a test user."""
    response = client.post(
        "/api/v1/auth/login",
        json={"username": test_user["username"], "password": test_user["password"]}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_user(client, db_session):
    """Create a test user."""
    from models.user import User
    from core.security import hash_password

    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "TestPassword123!",
    }

    # Check if user already exists
    existing_user = db_session.query(User).filter(User.username == user_data["username"]).first()
    if existing_user:
        return user_data

    user = User(
        username=user_data["username"],
        email=user_data["email"],
        hashed_password=hash_password(user_data["password"]),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    return user_data


@pytest.fixture
def mock_settings():
    """Mock settings for tests."""
    from core.config import Settings

    return Settings(
        jwt_secret_key=TEST_JWT_SECRET,
        app_env="test",
        app_host="127.0.0.1",
        redis_url="redis://localhost:6379/15",
    )
