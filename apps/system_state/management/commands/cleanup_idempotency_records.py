from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.system_state.models import IdempotencyRecord


class Command(BaseCommand):
    help = "Delete expired idempotency records. Run daily after the retention window."

    def handle(self, *args, **options):
        count, _ = IdempotencyRecord.objects.filter(expires_at__lt=timezone.now()).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} expired idempotency records."))
