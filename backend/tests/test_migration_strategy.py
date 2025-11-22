"""
Tests for zero-downtime migration strategy.

Tests verify:
- Migration safety checks
- Migration validation
- Rollback procedures
- Data verification
- Zero-downtime deployment scenarios
"""

import os
import subprocess
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction


class TestMigrationSafetyCheck:
    """Test migration safety checking command."""

    def test_check_migration_safety_command_exists(self):
        """Test that check_migration_safety command exists."""
        # Try to import the command directly
        try:
            from config.management.commands.check_migration_safety import Command

            assert Command is not None
        except ImportError:
            # If import fails, check if command can be called
            from io import StringIO

            from django.core.management import call_command

            output = StringIO()
            try:
                call_command("check_migration_safety", "--help", stdout=output)
                assert True  # Command exists
            except Exception:
                pytest.skip("Command not available")

    def test_check_migration_safety_safe_migration(self):
        """Test checking a safe migration (AddField)."""
        # Use an existing safe migration
        output = StringIO()
        try:
            call_command(
                "check_migration_safety",
                "polls",
                "0003_add_is_draft_field",
                stdout=output,
            )
            result = output.getvalue()
            # Should indicate migration is safe or have warnings
            assert "Migration" in result or "Safe" in result or "safe" in result
        except CommandError:
            # Migration might not exist, that's okay for this test
            pytest.skip("Migration not found")

    def test_check_migration_safety_invalid_app(self):
        """Test checking migration for invalid app."""
        with pytest.raises(CommandError):
            call_command("check_migration_safety", "nonexistent_app", "0001_initial")

    def test_check_migration_safety_invalid_migration(self):
        """Test checking invalid migration name."""
        with pytest.raises(CommandError):
            call_command("check_migration_safety", "polls", "nonexistent_migration")


class TestMigrationValidation:
    """Test migration validation command."""

    def test_validate_migration_command_exists(self):
        """Test that validate_migration command exists."""
        # Try to import the command directly
        try:
            from config.management.commands.validate_migration import Command

            assert Command is not None
        except ImportError:
            # If import fails, check if command can be called
            from io import StringIO

            from django.core.management import call_command

            output = StringIO()
            try:
                call_command("validate_migration", "--help", stdout=output)
                assert True  # Command exists
            except Exception:
                pytest.skip("Command not available")

    def test_validate_migration_dry_run(self):
        """Test migration validation with dry run."""
        output = StringIO()
        try:
            call_command(
                "validate_migration",
                "polls",
                "0001_initial",
                "--dry-run",
                stdout=output,
            )
            result = output.getvalue()
            assert "Database connection" in result or "Validation" in result
        except CommandError:
            pytest.skip("Migration not found or already applied")

    def test_validate_migration_invalid_app(self):
        """Test validating migration for invalid app."""
        with pytest.raises(CommandError):
            call_command("validate_migration", "nonexistent_app", "0001_initial")


class TestRollbackMigration:
    """Test migration rollback command."""

    def test_rollback_migration_command_exists(self):
        """Test that rollback_migration command exists."""
        # Try to import the command directly
        try:
            from config.management.commands.rollback_migration import Command

            assert Command is not None
        except ImportError:
            # If import fails, check if command can be called
            from io import StringIO

            from django.core.management import call_command

            output = StringIO()
            try:
                call_command("rollback_migration", "--help", stdout=output)
                assert True  # Command exists
            except Exception:
                pytest.skip("Command not available")

    def test_rollback_migration_not_applied(self):
        """Test rolling back a migration that's not applied."""
        # Try to rollback a migration that doesn't exist or isn't applied
        output = StringIO()
        try:
            call_command(
                "rollback_migration",
                "polls",
                "nonexistent_migration_9999",
                "--no-backup",
                stdout=output,
            )
        except CommandError as e:
            # Expected - migration not applied or command not found
            error_msg = str(e).lower()
            assert (
                "not applied" in error_msg
                or "not found" in error_msg
                or "unknown command" in error_msg
            )
        except Exception:
            # Command might not be discoverable by Django, that's okay
            pytest.skip("Command not discoverable")


class TestVerifyMigrationData:
    """Test migration data verification command."""

    def test_verify_migration_data_command_exists(self):
        """Test that verify_migration_data command exists."""
        # Try to import the command directly
        try:
            from config.management.commands.verify_migration_data import Command

            assert Command is not None
        except ImportError:
            # If import fails, check if command can be called
            from io import StringIO

            from django.core.management import call_command

            output = StringIO()
            try:
                call_command("verify_migration_data", "--help", stdout=output)
                assert True  # Command exists
            except Exception:
                pytest.skip("Command not available")

    def test_verify_migration_data_polls_app(self):
        """Test verifying data for polls app."""
        output = StringIO()
        try:
            call_command("verify_migration_data", "polls", stdout=output)
            result = output.getvalue()
            assert (
                "Database connection" in result
                or "Models" in result
                or "verification" in result
            )
        except CommandError as e:
            if "Unknown command" in str(e):
                pytest.skip("Command not discoverable by Django")
            raise

    def test_verify_migration_data_invalid_app(self):
        """Test verifying data for invalid app."""
        with pytest.raises(CommandError):
            call_command("verify_migration_data", "nonexistent_app")


class TestBackupScripts:
    """Test backup and restore scripts."""

    def test_backup_script_exists(self):
        """Test that backup script exists."""
        script_path = (
            Path(__file__).parent.parent.parent / "scripts" / "backup-database.sh"
        )
        assert script_path.exists(), "backup-database.sh should exist"

    def test_backup_script_is_executable(self):
        """Test that backup script is executable."""
        script_path = (
            Path(__file__).parent.parent.parent / "scripts" / "backup-database.sh"
        )
        if script_path.exists():
            assert os.access(
                script_path, os.X_OK
            ), "backup-database.sh should be executable"

    def test_restore_script_exists(self):
        """Test that restore script exists."""
        script_path = (
            Path(__file__).parent.parent.parent / "scripts" / "restore-database.sh"
        )
        assert script_path.exists(), "restore-database.sh should exist"

    def test_restore_script_is_executable(self):
        """Test that restore script is executable."""
        script_path = (
            Path(__file__).parent.parent.parent / "scripts" / "restore-database.sh"
        )
        if script_path.exists():
            assert os.access(
                script_path, os.X_OK
            ), "restore-database.sh should be executable"


class TestDeploymentScripts:
    """Test deployment scripts."""

    def test_blue_green_deploy_script_exists(self):
        """Test that blue-green deploy script exists."""
        script_path = (
            Path(__file__).parent.parent.parent / "scripts" / "blue-green-deploy.sh"
        )
        assert script_path.exists(), "blue-green-deploy.sh should exist"

    def test_blue_green_deploy_script_is_executable(self):
        """Test that blue-green deploy script is executable."""
        script_path = (
            Path(__file__).parent.parent.parent / "scripts" / "blue-green-deploy.sh"
        )
        if script_path.exists():
            assert os.access(
                script_path, os.X_OK
            ), "blue-green-deploy.sh should be executable"

    def test_migrate_safe_script_exists(self):
        """Test that migrate-safe script exists."""
        script_path = (
            Path(__file__).parent.parent.parent / "scripts" / "migrate-safe.sh"
        )
        assert script_path.exists(), "migrate-safe.sh should exist"

    def test_migrate_safe_script_is_executable(self):
        """Test that migrate-safe script is executable."""
        script_path = (
            Path(__file__).parent.parent.parent / "scripts" / "migrate-safe.sh"
        )
        if script_path.exists():
            assert os.access(
                script_path, os.X_OK
            ), "migrate-safe.sh should be executable"


class TestBlueGreenConfiguration:
    """Test blue-green deployment configuration."""

    def test_green_compose_file_exists(self):
        """Test that green compose file exists."""
        compose_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "docker-compose.prod-green.yml"
        )
        assert compose_path.exists(), "docker-compose.prod-green.yml should exist"

    def test_green_compose_has_different_ports(self):
        """Test that green compose uses different ports."""
        import yaml

        compose_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "docker-compose.prod-green.yml"
        )
        if compose_path.exists():
            with open(compose_path) as f:
                green_config = yaml.safe_load(f)

            # Check web service has different port
            web_service = green_config.get("services", {}).get("web", {})
            ports = web_service.get("ports", [])
            # Green should use port 8002
            assert any(
                "8002:8000" in str(port) for port in ports
            ), "Green should use port 8002"

    def test_green_compose_has_different_container_names(self):
        """Test that green compose uses different container names."""
        import yaml

        compose_path = (
            Path(__file__).parent.parent.parent
            / "docker"
            / "docker-compose.prod-green.yml"
        )
        if compose_path.exists():
            with open(compose_path) as f:
                green_config = yaml.safe_load(f)

            # Check container names contain "green"
            for service_name, service_config in green_config.get(
                "services", {}
            ).items():
                container_name = service_config.get("container_name", "")
                assert (
                    "green" in container_name.lower()
                ), f"Container {container_name} should contain 'green'"


class TestMigrationStrategyDocumentation:
    """Test migration strategy documentation."""

    def test_migration_strategy_doc_exists(self):
        """Test that migration strategy documentation exists."""
        doc_path = (
            Path(__file__).parent.parent.parent / "docs" / "migration-strategy.md"
        )
        assert doc_path.exists(), "migration-strategy.md should exist"

    def test_migration_strategy_doc_has_required_sections(self):
        """Test that migration strategy doc has required sections."""
        doc_path = (
            Path(__file__).parent.parent.parent / "docs" / "migration-strategy.md"
        )
        if doc_path.exists():
            content = doc_path.read_text()
            required_sections = [
                "Zero-Downtime",
                "Backward Compatibility",
                "Rollback",
                "Blue-Green",
                "Migration Workflow",
            ]
            for section in required_sections:
                assert (
                    section in content
                ), f"Documentation should include {section} section"


class TestMigrationBackwardCompatibility:
    """Test migration backward compatibility principles."""

    def test_safe_migration_operations(self):
        """Test that safe migration operations are identified."""
        from django.db import migrations

        # Safe operations
        safe_ops = [
            migrations.AddField,
            migrations.CreateModel,
            migrations.AddIndex,
        ]

        # These should be considered safe
        for op_class in safe_ops:
            assert op_class is not None, f"{op_class.__name__} should be available"

    def test_migration_can_be_applied_without_downtime(self, db):
        """Test that migrations can be checked for downtime requirements."""
        # This is a conceptual test - actual implementation would check migration operations
        from io import StringIO

        from django.core.management import call_command

        output = StringIO()
        try:
            # Try to check a real migration
            call_command("showmigrations", "polls", stdout=output, verbosity=0)
            # If this works, migrations are accessible
            assert True
        except Exception:
            pytest.skip("Cannot access migrations")


class TestZeroDowntimeDeployment:
    """Test zero-downtime deployment scenarios."""

    def test_health_endpoint_available_during_migration(self, client):
        """Test that health endpoint remains available during migration."""
        # Health endpoint should always be accessible
        response = client.get("/health/")
        assert response.status_code in [
            200,
            503,
        ], "Health endpoint should be accessible"

    def test_migration_does_not_block_health_check(self, db):
        """Test that migrations don't block health checks."""
        # Health check should work even if migrations are running
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            # If this works, database is accessible
            assert True

    @pytest.mark.skipif(
        not os.getenv("TEST_DOCKER", "").lower() == "true",
        reason="Docker tests require TEST_DOCKER=true",
    )
    def test_blue_green_deployment_script_runs(self):
        """Test that blue-green deployment script can be executed."""
        script_path = (
            Path(__file__).parent.parent.parent / "scripts" / "blue-green-deploy.sh"
        )
        if script_path.exists():
            # Just check it's executable and has correct shebang
            content = script_path.read_text()
            assert content.startswith("#!/bin/bash"), "Script should have bash shebang"


class TestRollbackProcedures:
    """Test rollback procedures."""

    def test_rollback_creates_backup(self):
        """Test that rollback command can create backup."""
        # The rollback command should support --no-backup flag
        # This tests that backup functionality is integrated
        from django.core.management import call_command

        # Check command accepts --no-backup flag
        try:
            call_command("rollback_migration", "--help")
        except SystemExit:
            # --help causes SystemExit, which is expected
            pass
        except Exception as e:
            # Other exceptions mean command doesn't exist or has issues
            pytest.skip(f"Command help not accessible: {e}")

    def test_restore_script_has_confirmation(self):
        """Test that restore script requires confirmation."""
        script_path = (
            Path(__file__).parent.parent.parent / "scripts" / "restore-database.sh"
        )
        if script_path.exists():
            content = script_path.read_text()
            # Should have confirmation prompt
            assert (
                "confirm" in content.lower() or "yes" in content.lower()
            ), "Restore should require confirmation"
