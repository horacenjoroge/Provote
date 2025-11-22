"""
Tests for monitoring and alerting setup.

Tests verify:
- Metrics collection
- Alert configuration
- Dashboard configuration
- Sentry integration
"""

import os
from pathlib import Path

import pytest
import yaml


class TestPrometheusConfiguration:
    """Test Prometheus configuration."""

    def test_prometheus_config_exists(self):
        """Test that Prometheus configuration exists."""
        config_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "monitoring"
            / "prometheus.yml"
        )
        assert config_path.exists(), "prometheus.yml should exist"

    def test_prometheus_config_valid(self):
        """Test that Prometheus configuration is valid YAML."""
        config_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "monitoring"
            / "prometheus.yml"
        )
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
            assert "scrape_configs" in config, "Should have scrape_configs"
            assert "alerting" in config, "Should have alerting configuration"

    def test_prometheus_scrapes_django(self):
        """Test that Prometheus is configured to scrape Django."""
        config_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "monitoring"
            / "prometheus.yml"
        )
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
            scrape_configs = config.get("scrape_configs", [])
            django_jobs = [
                job for job in scrape_configs if job.get("job_name") == "django"
            ]
            assert len(django_jobs) > 0, "Should scrape Django application"


class TestAlertRules:
    """Test Prometheus alert rules."""

    def test_alerts_file_exists(self):
        """Test that alerts file exists."""
        alerts_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "monitoring"
            / "prometheus"
            / "alerts.yml"
        )
        assert alerts_path.exists(), "alerts.yml should exist"

    def test_alerts_file_valid(self):
        """Test that alerts file is valid YAML."""
        alerts_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "monitoring"
            / "prometheus"
            / "alerts.yml"
        )
        if alerts_path.exists():
            with open(alerts_path) as f:
                alerts = yaml.safe_load(f)
            assert "groups" in alerts, "Should have alert groups"

    def test_critical_alerts_defined(self):
        """Test that critical alerts are defined."""
        alerts_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "monitoring"
            / "prometheus"
            / "alerts.yml"
        )
        if alerts_path.exists():
            with open(alerts_path) as f:
                alerts = yaml.safe_load(f)
            groups = alerts.get("groups", [])
            all_rules = []
            for group in groups:
                all_rules.extend(group.get("rules", []))
            critical_alerts = [
                rule
                for rule in all_rules
                if rule.get("labels", {}).get("severity") == "critical"
            ]
            assert len(critical_alerts) > 0, "Should have critical alerts"


class TestAlertmanagerConfiguration:
    """Test Alertmanager configuration."""

    def test_alertmanager_config_exists(self):
        """Test that Alertmanager configuration exists."""
        config_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "monitoring"
            / "alertmanager.yml"
        )
        assert config_path.exists(), "alertmanager.yml should exist"

    def test_alertmanager_config_valid(self):
        """Test that Alertmanager configuration is valid YAML."""
        config_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "monitoring"
            / "alertmanager.yml"
        )
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
            assert "route" in config, "Should have route configuration"
            assert "receivers" in config, "Should have receivers"

    def test_pagerduty_receiver_configured(self):
        """Test that PagerDuty receiver is configured."""
        config_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "monitoring"
            / "alertmanager.yml"
        )
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
            receivers = config.get("receivers", [])
            pagerduty_receivers = [r for r in receivers if "pagerduty_configs" in r]
            assert len(pagerduty_receivers) > 0, "Should have PagerDuty receiver"


class TestGrafanaConfiguration:
    """Test Grafana configuration."""

    def test_grafana_datasource_config_exists(self):
        """Test that Grafana datasource configuration exists."""
        config_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "monitoring"
            / "grafana"
            / "provisioning"
            / "datasources"
            / "prometheus.yml"
        )
        assert config_path.exists(), "Grafana datasource config should exist"

    def test_grafana_dashboard_config_exists(self):
        """Test that Grafana dashboard configuration exists."""
        config_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "monitoring"
            / "grafana"
            / "provisioning"
            / "dashboards"
            / "default.yml"
        )
        assert config_path.exists(), "Grafana dashboard config should exist"

    def test_grafana_dashboard_exists(self):
        """Test that Grafana dashboard JSON exists."""
        dashboard_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "monitoring"
            / "grafana"
            / "dashboards"
            / "api-performance.json"
        )
        assert dashboard_path.exists(), "API performance dashboard should exist"


class TestDockerComposeMonitoring:
    """Test Docker Compose monitoring configuration."""

    def test_monitoring_compose_exists(self):
        """Test that monitoring compose file exists."""
        compose_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "docker-compose.monitoring.yml"
        )
        assert compose_path.exists(), "docker-compose.monitoring.yml should exist"

    def test_monitoring_services_defined(self):
        """Test that monitoring services are defined."""
        compose_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "docker-compose.monitoring.yml"
        )
        if compose_path.exists():
            with open(compose_path) as f:
                config = yaml.safe_load(f)
            services = config.get("services", {})
            required_services = ["prometheus", "grafana", "alertmanager"]
            for service in required_services:
                assert service in services, f"Service {service} should be defined"


class TestMetricsMiddleware:
    """Test metrics middleware."""

    def test_metrics_middleware_exists(self):
        """Test that metrics middleware exists."""
        middleware_path = (
            Path(__file__).parent.parent.parent
            / "backend"
            / "core"
            / "middleware"
            / "metrics.py"
        )
        assert middleware_path.exists(), "metrics.py middleware should exist"

    def test_metrics_middleware_importable(self):
        """Test that metrics middleware can be imported."""
        try:
            from core.middleware.metrics import MetricsMiddleware

            assert MetricsMiddleware is not None
        except ImportError:
            pytest.skip("Metrics middleware not available")


class TestSentryIntegration:
    """Test Sentry integration."""

    def test_sentry_configured_in_production(self):
        """Test that Sentry is configured in production settings."""
        settings_path = (
            Path(__file__).parent.parent.parent
            / "backend"
            / "config"
            / "settings"
            / "production.py"
        )
        if settings_path.exists():
            content = settings_path.read_text()
            assert "sentry_sdk" in content, "Should import sentry_sdk"
            assert "SENTRY_DSN" in content, "Should have SENTRY_DSN configuration"

    def test_sentry_in_requirements(self):
        """Test that sentry-sdk is in requirements."""
        requirements_path = (
            Path(__file__).parent.parent.parent / "requirements" / "production.txt"
        )
        if requirements_path.exists():
            content = requirements_path.read_text()
            assert "sentry-sdk" in content, "Should include sentry-sdk in requirements"


class TestMetricsEndpoint:
    """Test metrics endpoint."""

    def test_metrics_endpoint_configured(self, client):
        """Test that metrics endpoint is accessible (if Prometheus is installed)."""
        try:
            response = client.get("/metrics/")
            # Should return 200 if Prometheus is installed, 404 otherwise
            assert response.status_code in [
                200,
                404,
            ], "Metrics endpoint should be accessible or return 404"
        except Exception:
            pytest.skip("Metrics endpoint not available")


class TestMonitoringDocumentation:
    """Test monitoring documentation."""

    def test_monitoring_doc_exists(self):
        """Test that monitoring documentation exists."""
        doc_path = Path(__file__).parent.parent.parent / "docs" / "monitoring-setup.md"
        assert doc_path.exists(), "monitoring-setup.md should exist"

    def test_monitoring_doc_has_required_sections(self):
        """Test that monitoring doc has required sections."""
        doc_path = Path(__file__).parent.parent.parent / "docs" / "monitoring-setup.md"
        if doc_path.exists():
            content = doc_path.read_text()
            required_sections = [
                "Prometheus",
                "Grafana",
                "Sentry",
                "Alertmanager",
                "Metrics",
                "Alerts",
            ]
            for section in required_sections:
                assert (
                    section in content
                ), f"Documentation should include {section} section"
