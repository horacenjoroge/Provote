"""
Management command to set up periodic scheduled polls task.
"""

from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, IntervalSchedule


class Command(BaseCommand):
    help = "Set up periodic task for processing scheduled polls"

    def handle(self, *args, **options):
        # Create interval schedule for every minute execution
        # This ensures polls are activated/closed promptly
        schedule, created = IntervalSchedule.objects.get_or_create(
            every=1,
            period=IntervalSchedule.MINUTES,
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Created interval schedule: every {schedule.every} {schedule.period}")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Using existing interval schedule: every {schedule.every} {schedule.period}")
            )

        # Create or update periodic task
        task, created = PeriodicTask.objects.get_or_create(
            name="Process Scheduled Polls",
            defaults={
                "task": "apps.polls.tasks.process_scheduled_polls",
                "interval": schedule,
                "enabled": True,
                "description": "Periodically check and activate/close scheduled polls",
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Created periodic task: {task.name}")
            )
        else:
            # Update existing task
            task.task = "apps.polls.tasks.process_scheduled_polls"
            task.interval = schedule
            task.enabled = True
            task.save()
            self.stdout.write(
                self.style.SUCCESS(f"Updated periodic task: {task.name}")
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nPeriodic scheduled polls task is {'enabled' if task.enabled else 'disabled'}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Task will run every {schedule.every} {schedule.period}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "\nThis task will:"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "  - Activate polls when their start time is reached"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "  - Close polls when their end time is reached"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "  - Send notifications to poll creators"
            )
        )

