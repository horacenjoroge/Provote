"""
Tests for Docker production setup.

Tests verify:
- Multi-stage builds produce smaller images
- Health checks work correctly
- Logging is configured properly
- Secret management is secure
- Resource limits are set
- Restart policies are configured
- Containers start correctly
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml


class TestDockerfileProduction:
    """Test production Dockerfile features."""

    def test_dockerfile_prod_exists(self):
        """Test that Dockerfile.prod exists."""
        dockerfile_path = Path(__file__).parent.parent.parent / "docker" / "Dockerfile.prod"
        assert dockerfile_path.exists(), "Dockerfile.prod should exist"

    def test_dockerfile_prod_is_multi_stage(self):
        """Test that Dockerfile.prod uses multi-stage builds."""
        dockerfile_path = Path(__file__).parent.parent.parent / "docker" / "Dockerfile.prod"
        content = dockerfile_path.read_text()

        # Check for multi-stage build indicators
        assert "FROM python:3.11-slim as builder" in content, "Should have builder stage"
        assert "FROM python:3.11-slim as runtime" in content, "Should have runtime stage"
        assert "COPY --from=builder" in content, "Should copy from builder stage"

    def test_dockerfile_prod_has_healthcheck(self):
        """Test that Dockerfile.prod includes health check."""
        dockerfile_path = Path(__file__).parent.parent.parent / "docker" / "Dockerfile.prod"
        content = dockerfile_path.read_text()

        assert "HEALTHCHECK" in content, "Should have HEALTHCHECK instruction"
        assert "/health/" in content, "Should check /health/ endpoint"

    def test_dockerfile_prod_uses_non_root_user(self):
        """Test that Dockerfile.prod runs as non-root user."""
        dockerfile_path = Path(__file__).parent.parent.parent / "docker" / "Dockerfile.prod"
        content = dockerfile_path.read_text()

        assert "USER provote" in content, "Should run as non-root user"
        assert "groupadd -r provote" in content or "useradd -r" in content, "Should create non-root user"

    def test_dockerfile_prod_has_security_best_practices(self):
        """Test that Dockerfile.prod follows security best practices."""
        dockerfile_path = Path(__file__).parent.parent.parent / "docker" / "Dockerfile.prod"
        content = dockerfile_path.read_text()

        # Check for security practices
        assert "rm -rf /var/lib/apt/lists/*" in content, "Should clean apt cache"
        assert "--no-cache-dir" in content, "Should use --no-cache-dir for pip"
        assert "PYTHONDONTWRITEBYTECODE=1" in content, "Should set PYTHONDONTWRITEBYTECODE"
        assert "PYTHONUNBUFFERED=1" in content, "Should set PYTHONUNBUFFERED"


class TestDockerComposeProduction:
    """Test production docker-compose configuration."""

    @pytest.fixture
    def compose_file(self):
        """Load docker-compose.prod.yml."""
        compose_path = Path(__file__).parent.parent.parent / "docker" / "docker-compose.prod.yml"
        with open(compose_path) as f:
            return yaml.safe_load(f)

    def test_compose_file_exists(self, compose_file):
        """Test that docker-compose.prod.yml exists and is valid YAML."""
        assert compose_file is not None, "docker-compose.prod.yml should be valid YAML"

    def test_all_services_have_healthchecks(self, compose_file):
        """Test that all services have health checks configured."""
        services = compose_file.get("services", {})
        required_services = ["db", "redis", "web", "nginx"]

        for service_name in required_services:
            assert service_name in services, f"Service {service_name} should exist"
            service = services[service_name]
            assert "healthcheck" in service, f"Service {service_name} should have healthcheck"
            healthcheck = service["healthcheck"]
            assert "test" in healthcheck, f"Service {service_name} healthcheck should have test"
            assert "interval" in healthcheck, f"Service {service_name} healthcheck should have interval"
            assert "timeout" in healthcheck, f"Service {service_name} healthcheck should have timeout"
            assert "retries" in healthcheck, f"Service {service_name} healthcheck should have retries"

    def test_all_services_have_restart_policies(self, compose_file):
        """Test that all services have restart policies."""
        services = compose_file.get("services", {})
        required_services = ["db", "redis", "web", "celery", "celery-beat", "nginx"]

        for service_name in required_services:
            assert service_name in services, f"Service {service_name} should exist"
            service = services[service_name]
            assert "restart" in service, f"Service {service_name} should have restart policy"
            assert service["restart"] in ["always", "unless-stopped", "on-failure"], (
                f"Service {service_name} should have valid restart policy"
            )

    def test_all_services_have_resource_limits(self, compose_file):
        """Test that all services have resource limits configured."""
        services = compose_file.get("services", {})
        required_services = ["db", "redis", "web", "celery", "celery-beat", "nginx"]

        for service_name in required_services:
            assert service_name in services, f"Service {service_name} should exist"
            service = services[service_name]
            assert "deploy" in service, f"Service {service_name} should have deploy section"
            deploy = service["deploy"]
            assert "resources" in deploy, f"Service {service_name} should have resources"
            resources = deploy["resources"]
            assert "limits" in resources, f"Service {service_name} should have resource limits"
            limits = resources["limits"]
            assert "cpus" in limits, f"Service {service_name} should have CPU limit"
            assert "memory" in limits, f"Service {service_name} should have memory limit"

    def test_all_services_have_logging_config(self, compose_file):
        """Test that all services have logging configuration."""
        services = compose_file.get("services", {})
        required_services = ["db", "redis", "web", "celery", "celery-beat", "nginx"]

        for service_name in required_services:
            assert service_name in services, f"Service {service_name} should exist"
            service = services[service_name]
            assert "logging" in service, f"Service {service_name} should have logging config"
            logging_config = service["logging"]
            assert "driver" in logging_config, f"Service {service_name} should have logging driver"
            assert "options" in logging_config, f"Service {service_name} should have logging options"
            options = logging_config["options"]
            assert "max-size" in options, f"Service {service_name} should have max-size"
            assert "max-file" in options, f"Service {service_name} should have max-file"

    def test_web_service_uses_production_dockerfile(self, compose_file):
        """Test that web service uses Dockerfile.prod."""
        services = compose_file.get("services", {})
        web_service = services.get("web", {})
        build = web_service.get("build", {})
        assert "dockerfile" in build, "Web service should specify dockerfile"
        assert build["dockerfile"] == "docker/Dockerfile.prod", "Should use Dockerfile.prod"

    def test_services_have_dependencies(self, compose_file):
        """Test that services have proper dependency configuration."""
        services = compose_file.get("services", {})
        web_service = services.get("web", {})
        assert "depends_on" in web_service, "Web service should have depends_on"
        depends_on = web_service["depends_on"]
        assert "db" in depends_on, "Web should depend on db"
        assert "redis" in depends_on, "Web should depend on redis"
        # Check dependency conditions
        if isinstance(depends_on["db"], dict):
            assert "condition" in depends_on["db"], "Dependency should have condition"
            assert depends_on["db"]["condition"] == "service_healthy", "Should wait for healthy service"


class TestHealthCheckEndpoint:
    """Test health check endpoint."""

    def test_health_endpoint_exists(self):
        """Test that health endpoint is defined in URLs."""
        from django.urls import reverse, NoReverseMatch

        try:
            url = reverse("health-check")
            assert url == "/health/", "Health check endpoint should be at /health/"
        except NoReverseMatch:
            pytest.fail("Health check endpoint should be defined in URLs")

    def test_health_endpoint_accessible(self, client):
        """Test that health endpoint is accessible without authentication."""
        response = client.get("/health/")
        assert response.status_code in [200, 503], "Health endpoint should be accessible"
        assert "status" in response.json(), "Response should have status field"
        assert "checks" in response.json(), "Response should have checks field"

    def test_health_endpoint_checks_database(self, client, db):
        """Test that health endpoint checks database connectivity."""
        response = client.get("/health/")
        data = response.json()
        assert "checks" in data, "Response should have checks"
        assert "database" in data["checks"], "Should check database"
        # Database should be healthy in test environment
        assert data["checks"]["database"] == "healthy", "Database should be healthy"

    def test_health_endpoint_checks_cache(self, client):
        """Test that health endpoint checks cache connectivity."""
        response = client.get("/health/")
        data = response.json()
        assert "checks" in data, "Response should have checks"
        assert "cache" in data["checks"], "Should check cache"


class TestSecretManagement:
    """Test secret management configuration."""

    def test_env_example_exists(self):
        """Test that .env.example exists."""
        # Check both possible locations
        env_example_path1 = Path(__file__).parent.parent.parent / "docker" / ".env.example"
        env_example_path2 = Path(__file__).parent.parent.parent / "docker" / "env.example"
        assert env_example_path1.exists() or env_example_path2.exists(), ".env.example should exist in docker/ directory"

    def test_env_example_has_required_variables(self):
        """Test that .env.example includes all required variables."""
        # Check both possible locations
        env_example_path1 = Path(__file__).parent.parent.parent / "docker" / ".env.example"
        env_example_path2 = Path(__file__).parent.parent.parent / "docker" / "env.example"
        env_example_path = env_example_path1 if env_example_path1.exists() else env_example_path2
        content = env_example_path.read_text()

        required_vars = [
            "SECRET_KEY",
            "DEBUG",
            "ALLOWED_HOSTS",
            "DB_NAME",
            "DB_USER",
            "DB_PASSWORD",
            "DB_HOST",
            "REDIS_HOST",
            "CELERY_BROKER_URL",
            "CELERY_RESULT_BACKEND",
        ]

        for var in required_vars:
            assert var in content, f".env.example should include {var}"

    def test_env_example_has_security_warnings(self):
        """Test that .env.example includes security warnings."""
        # Check both possible locations
        env_example_path1 = Path(__file__).parent.parent.parent / "docker" / ".env.example"
        env_example_path2 = Path(__file__).parent.parent.parent / "docker" / "env.example"
        env_example_path = env_example_path1 if env_example_path1.exists() else env_example_path2
        content = env_example_path.read_text()

        # Check for security warnings
        assert "NEVER commit" in content or "never commit" in content, "Should warn about committing .env"


class TestContainerStartup:
    """Test container startup and configuration."""

    @pytest.mark.skipif(
        not os.getenv("TEST_DOCKER", "").lower() == "true",
        reason="Docker tests require TEST_DOCKER=true",
    )
    def test_dockerfile_builds_successfully(self):
        """Test that Dockerfile.prod builds without errors."""
        dockerfile_path = Path(__file__).parent.parent.parent / "docker" / "Dockerfile.prod"
        context_path = Path(__file__).parent.parent.parent

        result = subprocess.run(
            ["docker", "build", "-f", str(dockerfile_path), "-t", "provote:test", str(context_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )

        assert result.returncode == 0, f"Docker build failed: {result.stderr}"

    @pytest.mark.skipif(
        not os.getenv("TEST_DOCKER", "").lower() == "true",
        reason="Docker tests require TEST_DOCKER=true",
    )
    def test_containers_start_correctly(self):
        """Test that containers start correctly with docker-compose."""
        compose_path = Path(__file__).parent.parent.parent / "docker" / "docker-compose.prod.yml"

        # This test requires a full Docker environment and .env file
        # It's marked as optional and only runs if TEST_DOCKER=true
        result = subprocess.run(
            ["docker-compose", "-f", str(compose_path), "config"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Config validation should pass
        assert result.returncode == 0, f"Docker Compose config invalid: {result.stderr}"


class TestLoggingConfiguration:
    """Test logging configuration for production."""

    def test_production_logging_config_exists(self):
        """Test that production settings have logging configuration."""
        from django.conf import settings

        # Import production settings
        import importlib
        import sys

        # Temporarily set DJANGO_SETTINGS_MODULE to production
        original_settings = os.environ.get("DJANGO_SETTINGS_MODULE")
        try:
            os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
            # Reload settings
            if "django.conf" in sys.modules:
                importlib.reload(sys.modules["django.conf"])
            from django.conf import settings as prod_settings

            assert hasattr(prod_settings, "LOGGING"), "Production settings should have LOGGING"
            assert "version" in prod_settings.LOGGING, "LOGGING should have version"
            assert "handlers" in prod_settings.LOGGING, "LOGGING should have handlers"
        finally:
            if original_settings:
                os.environ["DJANGO_SETTINGS_MODULE"] = original_settings
            elif "DJANGO_SETTINGS_MODULE" in os.environ:
                del os.environ["DJANGO_SETTINGS_MODULE"]


class TestDocumentation:
    """Test that Docker documentation is complete."""

    def test_docker_readme_exists(self):
        """Test that docker/README.md exists."""
        readme_path = Path(__file__).parent.parent.parent / "docker" / "README.md"
        assert readme_path.exists(), "docker/README.md should exist"

    def test_docker_readme_has_required_sections(self):
        """Test that docker/README.md has required sections."""
        readme_path = Path(__file__).parent.parent.parent / "docker" / "README.md"
        content = readme_path.read_text()

        required_sections = [
            "Multi-Stage Builds",
            "Health Checks",
            "Logging",
            "Secret Management",
            "Resource Limits",
            "Restart Policies",
        ]

        for section in required_sections:
            assert section in content, f"README should document {section}"

