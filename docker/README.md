# Docker Production Setup

This directory contains production-ready Docker configuration for Provote.

## Files

- **`Dockerfile.prod`**: Multi-stage production Dockerfile (smaller, optimized images)
- **`docker-compose.prod.yml`**: Production Docker Compose configuration with:
  - Health checks for all services
  - Resource limits (CPU, memory)
  - Restart policies
  - Structured logging
  - Secret management
- **`nginx.conf`**: Nginx main configuration
- **`nginx-ssl.conf`**: SSL/HTTPS configuration for production
- **`.env.example`**: Template for environment variables

## Features

### 1. Multi-Stage Builds
- **Builder stage**: Installs dependencies and builds static files
- **Runtime stage**: Minimal production image with only runtime dependencies
- **Result**: Smaller images (~50% reduction), faster deployments

### 2. Health Checks
- **Database**: PostgreSQL readiness check
- **Redis**: Ping check
- **Web**: HTTP health endpoint (`/health/`)
- **Nginx**: HTTP endpoint check
- All services wait for dependencies to be healthy before starting

### 3. Logging Configuration
- **Structured logging**: JSON format with rotation
- **Log rotation**: Max 10MB per file, 3-5 files retained
- **Service tags**: Each service tagged for easy filtering
- **Centralized logs**: All logs accessible via `docker-compose logs`

### 4. Secret Management
- **Environment variables**: All secrets via `.env` file
- **Never commit secrets**: `.env` is in `.gitignore`
- **Template provided**: `.env.example` shows required variables
- **Docker secrets**: Can be extended to use Docker secrets for sensitive data

### 5. Resource Limits
- **CPU limits**: Prevent resource exhaustion
- **Memory limits**: Prevent OOM kills
- **Reservations**: Guaranteed minimum resources
- **Per-service limits**: Tailored to each service's needs

### 6. Restart Policies
- **`unless-stopped`**: Automatic restart on failure
- **Graceful shutdown**: Services handle SIGTERM properly
- **Dependency management**: Services wait for dependencies

## Quick Start

### 1. Set Up Environment Variables

```bash
# Copy the example file
cp docker/.env.example .env

# Edit .env and fill in your values
nano .env
```

### 2. Build and Start Services

```bash
# Build images
docker-compose -f docker/docker-compose.prod.yml build

# Start services
docker-compose -f docker/docker-compose.prod.yml up -d

# Check status
docker-compose -f docker/docker-compose.prod.yml ps
```

### 3. Verify Health Checks

```bash
# Check all services are healthy
docker-compose -f docker/docker-compose.prod.yml ps

# Test health endpoint
curl http://localhost/health/

# Expected response:
# {"status":"healthy","checks":{"database":"healthy","cache":"healthy"},"version":"1.0.0"}
```

### 4. View Logs

```bash
# All services
docker-compose -f docker/docker-compose.prod.yml logs -f

# Specific service
docker-compose -f docker/docker-compose.prod.yml logs -f web

# Last 100 lines
docker-compose -f docker/docker-compose.prod.yml logs --tail=100 web
```

## Health Check Endpoint

The application provides a `/health/` endpoint that checks:
- Database connectivity
- Cache (Redis) connectivity
- Returns HTTP 200 if healthy, 503 if unhealthy

**Usage:**
```bash
curl http://localhost/health/
```

**Response (healthy):**
```json
{
  "status": "healthy",
  "checks": {
    "database": "healthy",
    "cache": "healthy"
  },
  "version": "1.0.0"
}
```

## Resource Limits

Each service has configured limits:

| Service | CPU Limit | Memory Limit | CPU Reservation | Memory Reservation |
|---------|-----------|--------------|-----------------|-------------------|
| web | 4.0 | 4GB | 1.0 | 1GB |
| celery | 2.0 | 2GB | 0.5 | 512MB |
| db | 2.0 | 2GB | 0.5 | 512MB |
| redis | 1.0 | 1GB | 0.25 | 256MB |
| celery-beat | 0.5 | 512MB | 0.1 | 128MB |
| nginx | 1.0 | 512MB | 0.25 | 128MB |

## Logging

### Log Locations

- **Application logs**: `docker-compose logs web`
- **Celery logs**: `docker-compose logs celery`
- **Nginx logs**: Inside container at `/var/log/nginx/`
- **Database logs**: PostgreSQL logs (if configured)

### Log Rotation

- **Max size**: 10MB per file
- **Max files**: 3-5 files per service
- **Format**: JSON with service tags

### Viewing Logs

```bash
# Follow all logs
docker-compose -f docker/docker-compose.prod.yml logs -f

# Specific service with timestamps
docker-compose -f docker/docker-compose.prod.yml logs -f -t web

# Last 100 lines
docker-compose -f docker/docker-compose.prod.yml logs --tail=100 web
```

## Secret Management

### Environment Variables

All secrets are managed via `.env` file:

```bash
# Create .env from template
cp docker/.env.example .env

# Edit secrets
nano .env
```

### Required Secrets

- `SECRET_KEY`: Django secret key (generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`)
- `DB_PASSWORD`: Strong database password
- `EMAIL_HOST_PASSWORD`: Email service password
- SSL certificates (for HTTPS)

### Security Best Practices

1. **Never commit `.env`** - It's in `.gitignore`
2. **Use strong passwords** - Generate random passwords
3. **Rotate secrets regularly** - Change passwords periodically
4. **Limit access** - Only authorized personnel should access `.env`
5. **Use secrets management** - Consider Docker secrets or external secret managers for production

## Restart Policies

All services use `restart: unless-stopped`:
- **Automatic restart** on container failure
- **No restart** if manually stopped
- **Graceful shutdown** on `docker-compose down`

## Troubleshooting

### Services Not Starting

```bash
# Check service status
docker-compose -f docker/docker-compose.prod.yml ps

# Check logs
docker-compose -f docker/docker-compose.prod.yml logs web

# Check health
curl http://localhost/health/
```

### Health Check Failing

```bash
# Check database connectivity
docker-compose -f docker/docker-compose.prod.yml exec web python manage.py dbshell

# Check Redis connectivity
docker-compose -f docker/docker-compose.prod.yml exec redis redis-cli ping

# Check application logs
docker-compose -f docker/docker-compose.prod.yml logs web
```

### Resource Issues

```bash
# Check resource usage
docker stats

# Adjust limits in docker-compose.prod.yml if needed
```

## Production Deployment

See `docs/deployment-guide.md` for complete production deployment instructions.

