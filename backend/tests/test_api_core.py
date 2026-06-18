def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Agentic DataLab API"
    assert data["status"] == "running"


def test_health_check(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "Agentic-DataLab"


def test_register_validation(client):
    # 测试弱密码被拒绝
    response = client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "weak"
    })
    assert response.status_code == 422


def test_register_strong_password(client):
    # 测试强密码通过验证
    response = client.post("/api/v1/auth/register", json={
        "username": "testuser123",
        "email": "test123@example.com",
        "password": "StrongPass123!@#"
    })
    # 可能返回 201 (成功) 或 409 (用户已存在)
    assert response.status_code in [201, 409]
