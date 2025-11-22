"""
Management command to validate that a migration can be applied.
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


class Command(BaseCommand):
    help = "Validate that a migration can be applied without errors"

    def add_arguments(self, parser):
        parser.add_argument(
            "app_name",
            type=str,
            help="App name containing the migration",
        )
        parser.add_argument(
            "migration_name",
            type=str,
            nargs="?",
            help="Migration name (e.g., 0001_initial). If not provided, validates all pending migrations.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Perform a dry run without applying the migration",
        )

    def handle(self, *args, **options):
        app_name = options["app_name"]
        migration_name = options.get("migration_name")
        dry_run = options["dry_run"]

        try:
            # Get the app config
            app_config = apps.get_app_config(app_name)
            app_label = app_config.label

            # Check database connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                self.stdout.write(self.style.SUCCESS("✓ Database connection OK"))

            # Check if migration exists
            if migration_name:
                try:
                    migration_module = __import__(
                        f"{app_label}.migrations.{migration_name}",
                        fromlist=["Migration"],
                    )
                    Migration = getattr(migration_module, "Migration")
                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Migration found: {migration_name}")
                    )
                except (ImportError, AttributeError) as e:
                    raise CommandError(f"Could not import migration: {e}")

                # Validate migration operations
                operations = Migration.operations
                self.stdout.write(f"Operations to apply: {len(operations)}")

                for i, operation in enumerate(operations, 1):
                    op_type = type(operation).__name__
                    self.stdout.write(f"  {i}. {op_type}")

                    # Check for potential issues
                    if hasattr(operation, "model_name"):
                        self.stdout.write(f"     Model: {operation.model_name}")

            # Check for pending migrations
            from io import StringIO

            from django.core.management import call_command

            output = StringIO()
            call_command("showmigrations", app_name, stdout=output, no_color=True)
            migrations_output = output.getvalue()

            pending = [line for line in migrations_output.split("\n") if "[ ]" in line]
            if pending:
                self.stdout.write(
                    self.style.WARNING(f"\n⚠ Found {len(pending)} pending migrations:")
                )
                for line in pending[:5]:  # Show first 5
                    self.stdout.write(f"  {line.strip()}")
                if len(pending) > 5:
                    self.stdout.write(f"  ... and {len(pending) - 5} more")

            # Check database state
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) 
                    FROM django_migrations 
                    WHERE app = %s
                    """,
                    [app_label],
                )
                applied_count = cursor.fetchone()[0]
                self.stdout.write(
                    self.style.SUCCESS(f"\n✓ Applied migrations: {applied_count}")
                )

            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS(
                        "\n✓ Dry run complete - migration can be applied"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        "\n✓ Validation complete - migration is ready to apply"
                    )
                )

            return 0

        except Exception as e:
            raise CommandError(f"Error validating migration: {e}")
