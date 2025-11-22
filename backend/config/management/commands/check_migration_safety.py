"""
Management command to check if a migration is safe to apply (backward compatible).
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Check if a migration is safe to apply (backward compatible)"

    def add_arguments(self, parser):
        parser.add_argument(
            "app_name",
            type=str,
            help="App name containing the migration",
        )
        parser.add_argument(
            "migration_name",
            type=str,
            help="Migration name (e.g., 0001_initial)",
        )
        parser.add_argument(
            "--detailed",
            action="store_true",
            help="Show detailed analysis",
        )

    def handle(self, *args, **options):
        app_name = options["app_name"]
        migration_name = options["migration_name"]
        detailed = options["detailed"]

        try:
            # Get the app config
            app_config = apps.get_app_config(app_name)
            app_label = app_config.label

            # Try to import the migration
            try:
                migration_module = __import__(
                    f"{app_label}.migrations.{migration_name}",
                    fromlist=["Migration"],
                )
                Migration = getattr(migration_module, "Migration")
            except (ImportError, AttributeError) as e:
                raise CommandError(f"Could not import migration: {e}")

            # Analyze migration operations
            operations = Migration.operations
            issues = []
            warnings = []
            safe_operations = []

            for operation in operations:
                op_type = type(operation).__name__

                # Check for safe operations
                if op_type in [
                    "AddField",
                    "CreateModel",
                    "AddIndex",
                    "CreateIndex",
                    "RunPython",  # Data migrations are generally safe
                ]:
                    safe_operations.append(op_type)
                    continue

                # Check for potentially risky operations
                if op_type in [
                    "RemoveField",
                    "DeleteModel",
                    "RemoveIndex",
                    "DeleteIndex",
                ]:
                    warnings.append(
                        f"{op_type}: Requires code deployment before migration"
                    )
                    continue

                # Check for dangerous operations
                if op_type in [
                    "RenameField",
                    "RenameModel",
                    "AlterField",
                    "AlterModelTable",
                ]:
                    issues.append(
                        f"{op_type}: May require coordinated deployment and downtime"
                    )
                    continue

                # Unknown operation - warn
                warnings.append(f"{op_type}: Unknown operation type")

            # Report results
            self.stdout.write(self.style.SUCCESS("\n=== Migration Safety Analysis ==="))
            self.stdout.write(f"App: {app_name}")
            self.stdout.write(f"Migration: {migration_name}")
            self.stdout.write("")

            if safe_operations:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Safe operations: {', '.join(set(safe_operations))}"
                    )
                )

            if warnings:
                self.stdout.write(self.style.WARNING(f"⚠ Warnings: {len(warnings)}"))
                if detailed:
                    for warning in warnings:
                        self.stdout.write(f"  - {warning}")

            if issues:
                self.stdout.write(self.style.ERROR(f"✗ Issues: {len(issues)}"))
                for issue in issues:
                    self.stdout.write(f"  - {issue}")

            # Overall assessment
            self.stdout.write("")
            if issues:
                self.stdout.write(
                    self.style.ERROR(
                        "✗ Migration is NOT safe for zero-downtime deployment"
                    )
                )
                self.stdout.write(
                    "   Review issues above and plan for maintenance window"
                )
                return 1
            elif warnings:
                self.stdout.write(
                    self.style.WARNING("⚠ Migration requires careful planning")
                )
                self.stdout.write(
                    "   Review warnings and ensure code is deployed first if needed"
                )
                return 0
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        "✓ Migration is safe for zero-downtime deployment"
                    )
                )
                return 0

        except Exception as e:
            raise CommandError(f"Error checking migration safety: {e}")
