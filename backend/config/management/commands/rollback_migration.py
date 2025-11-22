"""
Management command to rollback a specific migration.
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


class Command(BaseCommand):
    help = "Rollback a specific migration to its previous state"

    def add_arguments(self, parser):
        parser.add_argument(
            "app_name",
            type=str,
            help="App name containing the migration",
        )
        parser.add_argument(
            "migration_name",
            type=str,
            help="Migration name to rollback (e.g., 0001_initial)",
        )
        parser.add_argument(
            "--target",
            type=str,
            help="Target migration to rollback to (defaults to previous migration)",
        )
        parser.add_argument(
            "--fake",
            action="store_true",
            help="Mark migration as unapplied without running it",
        )
        parser.add_argument(
            "--no-backup",
            action="store_true",
            help="Skip creating backup before rollback",
        )

    def handle(self, *args, **options):
        app_name = options["app_name"]
        migration_name = options["migration_name"]
        target = options.get("target")
        fake = options["fake"]
        no_backup = options["no_backup"]

        try:
            # Get the app config
            app_config = apps.get_app_config(app_name)
            app_label = app_config.label

            # Check if migration is applied
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) 
                    FROM django_migrations 
                    WHERE app = %s AND name = %s
                    """,
                    [app_label, migration_name],
                )
                is_applied = cursor.fetchone()[0] > 0

                if not is_applied:
                    raise CommandError(
                        f"Migration {migration_name} is not applied. Nothing to rollback."
                    )

            # Create backup unless disabled
            if not no_backup:
                self.stdout.write("Creating backup before rollback...")
                import os
                import subprocess

                script_path = os.path.join(
                    os.path.dirname(
                        os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                    ),
                    "scripts",
                    "backup-database.sh",
                )
                if os.path.exists(script_path):
                    result = subprocess.run(
                        ["bash", script_path, "--pre-migration"],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        self.stdout.write(
                            self.style.SUCCESS("✓ Backup created successfully")
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(f"⚠ Backup failed: {result.stderr}")
                        )
                        if input("Continue without backup? (yes/no): ") != "yes":
                            raise CommandError("Rollback cancelled")
                else:
                    self.stdout.write(
                        self.style.WARNING("⚠ Backup script not found, skipping backup")
                    )

            # Determine target migration
            if not target:
                # Find previous migration
                from io import StringIO

                from django.core.management import call_command

                output = StringIO()
                call_command("showmigrations", app_name, stdout=output, no_color=True)
                migrations_output = output.getvalue()

                # Parse applied migrations
                applied = []
                for line in migrations_output.split("\n"):
                    if "[X]" in line:
                        migration = line.strip().split()[-1]
                        applied.append(migration)

                # Find current migration index
                try:
                    current_index = applied.index(migration_name)
                    if current_index > 0:
                        target = applied[current_index - 1]
                    else:
                        target = "zero"  # Rollback all migrations
                except ValueError:
                    raise CommandError(
                        f"Migration {migration_name} not found in applied migrations"
                    )

            self.stdout.write(f"\nRolling back {app_name}.{migration_name}")
            if target != "zero":
                self.stdout.write(f"Target: {app_name}.{target}")
            else:
                self.stdout.write("Target: zero (unapply all migrations)")

            # Confirm
            if not fake:
                confirm = input("\nThis will modify the database. Continue? (yes/no): ")
                if confirm != "yes":
                    raise CommandError("Rollback cancelled")

            # Perform rollback
            from django.core.management import call_command

            migrate_args = [app_name, target]
            if fake:
                migrate_args.append("--fake")

            self.stdout.write("\nExecuting rollback...")
            call_command("migrate", *migrate_args, verbosity=1)

            self.stdout.write(
                self.style.SUCCESS(f"\n✓ Successfully rolled back to {target}")
            )

            # Verify
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) 
                    FROM django_migrations 
                    WHERE app = %s AND name = %s
                    """,
                    [app_label, migration_name],
                )
                is_still_applied = cursor.fetchone()[0] > 0

                if is_still_applied and not fake:
                    self.stdout.write(
                        self.style.WARNING(
                            f"⚠ Migration {migration_name} is still marked as applied"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Migration {migration_name} has been rolled back"
                        )
                    )

            return 0

        except Exception as e:
            raise CommandError(f"Error rolling back migration: {e}")
