# Use Python 3.11 slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements/ /app/requirements/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements/development.txt

# Copy project
COPY backend/ /app/backend/
COPY docker/ /app/docker/

# Set PYTHONPATH to include backend directory
ENV PYTHONPATH=/app/backend:$PYTHONPATH

# Change to backend directory for Django commands
WORKDIR /app/backend

# Collect static files
RUN python manage.py collectstatic --noinput --settings=config.settings.development || true

# Create directories for static and media files
RUN mkdir -p /app/backend/staticfiles /app/backend/media

# Expose port
EXPOSE 8000

# Run gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "config.wsgi:application"]

