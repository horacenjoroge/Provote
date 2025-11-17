"""
Management command to automatically unblock expired IPs.

This command should be run periodically (e.g., via cron or Celery beat)
to unblock IPs whose auto-unblock time has passed.
"""

from django.core.management.base import BaseCommand

from core.utils.ip_reputation import auto_unblock_expired_ips


class Command(BaseCommand):
    """Command to unblock expired IPs."""

    help = "Unblock IP addresses whose auto-unblock time has passed"

    def handle(self, *args, **options):
        """Execute the command."""
        count = auto_unblock_expired_ips()
        
        if count > 0:
            self.stdout.write(
                self.style.SUCCESS(f"Successfully unblocked {count} IP(s)")
            )
        else:
            self.stdout.write("No expired IPs to unblock")

