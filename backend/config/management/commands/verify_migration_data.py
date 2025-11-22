"""
Management command to verify data integrity after a migration.
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Verify data integrity after a migration"

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
            help="Migration name to verify (optional)",
        )
        parser.add_argument(
            "--check-constraints",
            action="store_true",
            help="Check database constraints",
        )
        parser.add_argument(
            "--check-indexes",
            action="store_true",
            help="Check database indexes",
        )

    def handle(self, *args, **options):
        app_name = options["app_name"]
        migration_name = options.get("migration_name")
        check_constraints = options["check_constraints"]
        check_indexes = options["check_indexes"]

        try:
            # Get the app config
            app_config = apps.get_app_config(app_name)
            app_label = app_config.label

            self.stdout.write(
                self.style.SUCCESS("\n=== Migration Data Verification ===")
            )
            self.stdout.write(f"App: {app_name}")

            # Check database connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                self.stdout.write(self.style.SUCCESS("✓ Database connection OK"))

            # Get all models for the app
            models = app_config.get_models()
            model_count = len(list(models))

            self.stdout.write(f"\nModels in app: {model_count}")

            # Check each model
            issues = []
            for model in models:
                model_name = model.__name__
                table_name = model._meta.db_table

                try:
                    with connection.cursor() as cursor:
                        # Check if table exists
                        cursor.execute(
                            """
                            SELECT EXISTS (
                                SELECT FROM information_schema.tables
                                WHERE table_schema = 'public'
                                AND table_name = %s
                            )
                            """,
                            [table_name],
                        )
                        table_exists = cursor.fetchone()[0]

                        if not table_exists:
                            issues.append(f"Table {table_name} does not exist")
                            continue

                        # Count records
                        # nosec B608: table_name comes from Django ORM introspection, not user input
                        cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')  # nosec B608
                        record_count = cursor.fetchone()[0]

                        self.stdout.write(f"  ✓ {model_name}: {record_count} records")

                        # Check for NULL in non-nullable fields
                        for field in model._meta.get_fields():
                            if (
                                hasattr(field, "null")
                                and not field.null
                                and hasattr(field, "column")
                            ):
                                # nosec B608: table_name and field.column come from Django ORM introspection, not user input
                                cursor.execute(
                                    f'SELECT COUNT(*) FROM "{table_name}" WHERE "{field.column}" IS NULL'  # nosec B608
                                )
                                null_count = cursor.fetchone()[0]
                                if null_count > 0:
                                    issues.append(
                                        f"{model_name}.{field.name}: {null_count} NULL values in non-nullable field"
                                    )

                except Exception as e:
                    issues.append(f"Error checking {model_name}: {e}")

            # Check constraints if requested
            if check_constraints:
                self.stdout.write("\nChecking constraints...")
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT conname, contype, conrelid::regclass
                        FROM pg_constraint
                        WHERE connamespace = 'public'::regnamespace
                        ORDER BY conrelid, conname
                        """
                    )
                    constraints = cursor.fetchall()
                    self.stdout.write(f"  Found {len(constraints)} constraints")

            # Check indexes if requested
            if check_indexes:
                self.stdout.write("\nChecking indexes...")
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT indexname, tablename
                        FROM pg_indexes
                        WHERE schemaname = 'public'
                        ORDER BY tablename, indexname
                        """
                    )
                    indexes = cursor.fetchall()
                    self.stdout.write(f"  Found {len(indexes)} indexes")

            # Report results
            self.stdout.write("")
            if issues:
                self.stdout.write(self.style.ERROR(f"\n✗ Found {len(issues)} issues:"))
                for issue in issues:
                    self.stdout.write(f"  - {issue}")
                return 1
            else:
                self.stdout.write(
                    self.style.SUCCESS("\n✓ Data verification passed - no issues found")
                )
                return 0

        except Exception as e:
            raise CommandError(f"Error verifying migration data: {e}")
