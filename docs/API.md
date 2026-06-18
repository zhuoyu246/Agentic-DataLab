# API Documentation

Base URL: `/api/v1`

## Authentication

### Register
```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "username": "string (3-50 chars)",
  "email": "string (valid email)",
  "password": "string (min 12 chars, must include: uppercase, lowercase, digit, special char)"
}

Response: 201 Created
{
  "access_token": "string",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "string",
    "email": "string",
    "is_active": true,
    "is_admin": false,
    "created_at": "2026-06-18T00:00:00"
  }
}
```

### Login
```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "string",
  "password": "string"
}

Response: 200 OK
{
  "access_token": "string",
  "token_type": "bearer",
  "user": { ... }
}
```

### Get Current User
```http
GET /api/v1/auth/me
Authorization: Bearer <token>

Response: 200 OK
{
  "id": 1,
  "username": "string",
  "email": "string",
  "is_active": true,
  "is_admin": false,
  "created_at": "2026-06-18T00:00:00"
}
```

## Sessions

### Create Session
```http
POST /api/v1/sessions
Authorization: Bearer <token>
Content-Type: application/json

{
  "project_id": "optional-project-id"
}

Response: 201 Created
{
  "session_id": "uuid",
  "created_at": "2026-06-18T00:00:00",
  "status": "active"
}
```

### List Sessions
```http
GET /api/v1/sessions
Authorization: Bearer <token>

Response: 200 OK
{
  "sessions": [
    {
      "session_id": "uuid",
      "title": "string",
      "created_at": "2026-06-18T00:00:00",
      "status": "active"
    }
  ]
}
```

## Chat

### Send Message (SSE)
```http
POST /api/v1/chat/stream
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "uuid",
  "message": "string"
}

Response: 200 OK (Server-Sent Events)
data: {"event_type": "thinking", "content": "Analyzing..."}
data: {"event_type": "message", "content": "Result", "agent": "supervisor"}
```

## Datasets

### Upload Dataset
```http
POST /api/v1/datasets/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: <binary>
session_id: "uuid"

Response: 201 Created
{
  "name": "data.csv",
  "path": "/path/to/data.csv",
  "rows": 1000,
  "columns": 10,
  "size_mb": 1.5
}
```

## Health

### Health Check
```http
GET /api/v1/health

Response: 200 OK
{
  "status": "healthy",
  "services": {
    "database": true,
    "redis": true,
    "llm": true
  },
  "timestamp": "2026-06-18T00:00:00"
}
```

## Rate Limits

- **Login**: 5 requests/minute per IP
- **Register**: 3 requests/hour per IP
- **Chat**: 20 requests/minute per IP
- **Upload**: 10 requests/minute per IP
- **Default**: 60 requests/minute per IP

## Error Responses

All errors follow this format:
```json
{
  "error": "ErrorType",
  "message": "Human-readable message",
  "details": {},
  "path": "/api/v1/endpoint"
}
```

Common status codes:
- `400` - Validation error
- `401` - Authentication required
- `403` - Permission denied
- `404` - Resource not found
- `409` - Resource conflict
- `422` - Invalid request data
- `429` - Rate limit exceeded
- `500` - Internal server error
- `503` - Service unavailable
