# Docker Quick Start Guide

## Prerequisites
- Docker Engine 20.10+
- Docker Compose V2+
- At least 4GB RAM available

## Quick Start

### 1. Generate JWT Secret Key
```bash
# Generate a secure JWT secret key
python backend/scripts/generate_secret.py

# Or use Python directly
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Create Environment File
```bash
# Copy the example environment file
cp backend/.env.example backend/.env

# Edit backend/.env and set your JWT_SECRET_KEY
# JWT_SECRET_KEY=<paste-your-generated-key-here>
```

### 3. Build and Start Services
```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Check service status
docker-compose ps
```

### 4. Access the Application
- Frontend: http://localhost:80
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs
- MLflow UI: http://localhost:5000

## Service Management

### Stop Services
```bash
docker-compose down
```

### Stop and Remove Volumes (⚠️ Deletes all data)
```bash
docker-compose down -v
```

### Rebuild Services
```bash
# Rebuild specific service
docker-compose build backend

# Rebuild all services
docker-compose build

# Force rebuild and restart
docker-compose up -d --build
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
```

### Execute Commands in Containers
```bash
# Backend shell
docker-compose exec backend bash

# Run database migrations
docker-compose exec backend alembic upgrade head

# Frontend shell
docker-compose exec frontend sh
```

## Troubleshooting

### Backend won't start - JWT Secret Key Error
**Problem**: Backend container exits with JWT secret key validation error.

**Solution**:
1. Generate a secure key: `python backend/scripts/generate_secret.py`
2. Update `backend/.env` with the generated key
3. Restart: `docker-compose restart backend`

### Database Connection Error
**Problem**: Backend can't connect to PostgreSQL.

**Solution**:
```bash
# Check if postgres is healthy
docker-compose ps postgres

# View postgres logs
docker-compose logs postgres

# Restart postgres
docker-compose restart postgres
```

### Port Already in Use
**Problem**: Port 80, 5432, 6379, or 8000 is already in use.

**Solution**: Edit `docker-compose.yml` and change port mappings:
```yaml
ports:
  - "8080:80"  # Change frontend port to 8080
```

### Clear All Data and Reset
```bash
# Stop everything
docker-compose down

# Remove volumes (⚠️ THIS DELETES ALL DATA)
docker-compose down -v

# Remove all images
docker-compose down --rmi all

# Start fresh
docker-compose up -d --build
```

## Production Deployment

### Security Checklist
- [ ] Generate strong JWT_SECRET_KEY (min 32 chars, cryptographically random)
- [ ] Change default PostgreSQL password
- [ ] Set strong Redis password (add to redis command in docker-compose.yml)
- [ ] Use environment-specific .env files (.env.production)
- [ ] Enable HTTPS/TLS (add Nginx reverse proxy with SSL)
- [ ] Restrict network access (use firewall rules)
- [ ] Regular backups of postgres_data and backend_storage volumes

### Recommended docker-compose.prod.yml Changes
```yaml
services:
  postgres:
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}  # Set via environment

  redis:
    command: redis-server --requirepass ${REDIS_PASSWORD}

  backend:
    environment:
      - APP_ENV=production
      - REDIS_URL=redis://redis:6379/0?password=${REDIS_PASSWORD}
```

## Monitoring

### Health Checks
```bash
# Check all services health
docker-compose ps

# Backend health endpoint
curl http://localhost:8000/api/v1/health

# Frontend health
curl http://localhost:80/
```

### Resource Usage
```bash
# View CPU/Memory usage
docker stats

# View specific service
docker stats agentic-datalab-backend
```

## Backup and Restore

### Backup Volumes
```bash
# Backup postgres data
docker run --rm -v agentic-datalab_postgres_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/postgres-backup-$(date +%Y%m%d).tar.gz /data

# Backup backend storage
docker run --rm -v agentic-datalab_backend_storage:/data -v $(pwd):/backup \
  alpine tar czf /backup/storage-backup-$(date +%Y%m%d).tar.gz /data
```

### Restore Volumes
```bash
# Restore postgres data
docker run --rm -v agentic-datalab_postgres_data:/data -v $(pwd):/backup \
  alpine sh -c "cd /data && tar xzf /backup/postgres-backup-YYYYMMDD.tar.gz --strip 1"
```

## Development Mode

For development with hot-reload:

```bash
# Use docker-compose with volume mounts (already configured)
docker-compose up -d

# Backend auto-reloads on code changes (volume mounted)
# Frontend needs rebuild: docker-compose build frontend
```

For local development without Docker, see `README.md`.
